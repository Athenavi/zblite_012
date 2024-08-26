import configparser
import csv
import logging
import os
import random
import time
import urllib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import requests
from flask import Flask, render_template, session, request, url_for, Response, jsonify, send_file, \
    make_response, send_from_directory
from flask_caching import Cache
from jinja2 import select_autoescape
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import safe_join

from src.BlogDeal import get_article_names, get_article_content, clear_html_format, \
    get_file_date, get_blog_author, read_hidden_articles, auth_articles, \
    zy_show_article
from src.utils import get_client_ip, read_file

global_encoding = 'utf-8'

app = Flask(__name__, template_folder='../templates', static_folder="../static")
app.config['CACHE_TYPE'] = 'simple'
cache = Cache(app)
app.secret_key = 'your_secret_key'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=3)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1)  # 添加 ProxyFix 中间件

# 移除默认的日志处理程序
app.logger.handlers = []

# 配置 Jinja2 环境
app.jinja_env.autoescape = select_autoescape(['html', 'xml'])
app.jinja_env.add_extension('jinja2.ext.loopcontrols')

# 新增日志处理程序
log_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
file_handler = logging.FileHandler('app.log', encoding=global_encoding)
file_handler.setFormatter(log_formatter)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
# 应用分享配置参数
domain = os.environ.get('DOMAIN', 'http://127.0.0.1:80/')
title = os.environ.get('BLOG_TITLE', 'zb-lite')


@app.route('/toggle_theme', methods=['POST'])  # 处理切换主题的请求
def toggle_theme():
    if session['theme'] == 'day-theme':
        session['theme'] = 'night-theme'  # 如果当前主题为白天，则切换为夜晚（night-theme）
    else:
        session['theme'] = 'day-theme'  # 如果当前主题为夜晚，则切换为白天（day-theme）

    return 'success'  # 返回切换成功的消息


def analyze_ip_location(ip_address):
    city_name = session.get('city_name')
    city_code = session.get('city_code')
    if city_name and city_code:
        return city_name, city_code
    else:
        ip_api_url = f'http://whois.pconline.com.cn/ipJson.jsp?ip={ip_address}&json=true'
        response = requests.get(ip_api_url)
        data = response.json()
        city_name = data.get('city')
        city_code = data.get('cityCode')
        session['city_name'] = city_name
        session['city_code'] = city_code
        return city_name, city_code


def get_unique_tags(csv_filename):
    tags = []
    with open(csv_filename, 'r', encoding=global_encoding) as file:
        reader = csv.reader(file)
        next(reader)  # Skip the header line
        for row in reader:
            tags.extend(row[1:])  # Append tags from the row (excluding the article name)

    unique_tags = list(set(tags))  # Remove duplicates
    return unique_tags


def get_articles_by_tag(csv_filename, tag_name):
    tag_articles = []
    with open(csv_filename, 'r', encoding=global_encoding) as file:
        reader = csv.reader(file)
        next(reader)  # Skip the header line
        for row in reader:
            if tag_name in row[1:]:
                tag_articles.append(row[0])  # Append the article name

    return tag_articles


def get_tags_by_article(csv_filename, article_name):
    tags = []
    with open(csv_filename, 'r', encoding=global_encoding) as file:
        reader = csv.reader(file)
        next(reader)  # Skip the header line
        for row in reader:
            if row[0] == article_name:
                tags.extend(row[1:])  # Append tags from the row (excluding the article name)
                break  # Break the loop if the article is found

    unique_tags = list(set(tags))  # Remove duplicates
    unique_tags = [tag for tag in unique_tags if tag]  # Remove empty tags
    return unique_tags


def get_list_intersection(list1, list2):
    intersection = list(set(list1) & set(list2))
    return intersection


# 主页
@app.route('/', methods=['GET', 'POST'])
def home():
    # 获取客户端IP地址
    ip = get_client_ip(request, session)
    city_name, city_code = analyze_ip_location(ip)
    if request.method == 'GET':
        page = request.args.get('page', default=1, type=int)
        tag = request.args.get('tag')

        if page <= 0:
            page = 1

        theme = session.get('theme', 'day-theme')  # 获取当前主题
        cache_key = f'page_content:{page}:{theme}:{tag}'  # 根据页面值和主题,标签生成缓存键

        # 从缓存中获取页面内容
        content = cache.get(cache_key)
        if content is not None:
            return content

        # 重新获取页面内容
        articles, has_next_page, has_previous_page = get_article_names(page=page)
        template = app.jinja_env.get_template('zyhome.html')
        session.setdefault('theme', 'day-theme')
        notice = read_file('notice/1.txt', 50)
        tags = get_unique_tags('articles/tags.csv')
        if tag:
            tag_articles = get_articles_by_tag('articles/tags.csv', tag)
            articles = get_list_intersection(articles, tag_articles)

        # 获取用户名
        username = session.get('username')
        app.logger.info('当前访问的用户:{}, IP:{}, IP归属地:{},城市代码:{}'.format(username, ip, city_name, city_code))

        # 渲染模板并存储渲染后的页面内容到缓存中
        rendered_content = template.render(
            title=title, articles=articles, url_for=url_for, theme=session['theme'], IPinfo=city_name,
            notice=notice, has_next_page=has_next_page, has_previous_page=has_previous_page,
            current_page=page, city_code=city_code, username=username, tags=tags
        )
        # 将渲染后的页面内容保存到缓存，并设置过期时间
        cache.set(cache_key, rendered_content, timeout=30)
        resp = make_response(rendered_content)
        if username is None:
            username = 'qks' + format(random.randint(1000, 9999))  # 可以设置一个默认值或者抛出异常，具体根据需求进行处理

        resp.set_cookie('key', 'zyBLOG' + username, 7200)
        # 设置 cookie
        return resp

    else:
        return render_template('zyhome.html')


@app.route('/blog/<article>', methods=['GET', 'POST'])
@app.route('/blog/<article>.html', methods=['GET', 'POST'])
def blog_detail(article):
    try:
        # 根据文章名称获取相应的内容并处理
        article_name = article
        article_names = get_article_names()
        hidden_articles = read_hidden_articles()

        if article_name in hidden_articles:
            # 隐藏的文章
            return vip_blog(article_name)

        if article_name not in article_names[0]:
            return render_template('error.html', status_code='404'), 404

        # 通过关键字缓存内容
        @cache.cached(timeout=180, key_prefix=f"article_{article_name}")
        def get_article_content_cached():
            return get_article_content(article, 215)

        article_tags = get_tags_by_article('articles/tags.csv', article_name)
        article_content, readNav_html = get_article_content_cached()
        article_summary = clear_html_format(article_content)[:30]

        article_Surl = domain + 'blog/' + article_name
        article_url = "https://api.7trees.cn/qrcode/?data=" + article_Surl
        author = get_blog_author(article_name)
        blogDate = get_file_date(article_name)
        theme = session.get('theme', 'day-theme')  # 获取当前主题

        response = make_response(render_template('zyDetail.html', title=title, article_content=article_content,
                                                 articleName=article_name, theme=theme,
                                                 author=author, blogDate=blogDate,
                                                 url_for=url_for, article_url=article_url,
                                                 article_Surl=article_Surl, article_summary=article_summary,
                                                 readNav=readNav_html, article_tags=article_tags, key="欢迎访问"))

        # 设置服务器端缓存时间
        response.cache_control.max_age = 180
        response.expires = datetime.now() + timedelta(seconds=180)

        # Set client-side cache time
        response.headers['Cache-Control'] = 'public, max-age=180'

        return response

    except FileNotFoundError:
        return render_template('error.html', status_code='404'), 404


# 创建全局变量来存储 sitemap 数据的缓存和时间戳
sitemap_cache = {
    'data': None,
    'timestamp': None
}


@app.route('/sitemap.xml')
@app.route('/sitemap')
def generate_sitemap():
    global sitemap_cache

    # 检查缓存是否存在且在一个小时之内
    if (
            sitemap_cache['data'] is not None and
            sitemap_cache['timestamp'] is not None and
            time.time() - sitemap_cache['timestamp'] < 3600
    ):
        return Response(sitemap_cache['data'], mimetype='text/xml')

    files = os.listdir('articles')
    markdown_files = [file for file in files if file.endswith('.md')]

    # 创建XML文件头
    xml_data = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_data += '<?xml-stylesheet type="text/xsl" href="./static/sitemap.xsl"?>\n'
    xml_data += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    for file in markdown_files:
        article_name = file[:-3]  # 移除文件扩展名 (.md)
        article_url = domain + 'blog/' + article_name
        date = get_file_date(article_name)

        # 创建url标签并包含链接
        xml_data += '<url>\n'
        xml_data += f'\t<loc>{article_url}</loc>\n'
        xml_data += f'\t<lastmod>{date}</lastmod>\n'  # 添加适当的标签
        xml_data += '\t<changefreq>Monthly</changefreq>\n'  # 添加适当的标签
        xml_data += '\t<priority>0.8</priority>\n'  # 添加适当的标签
        xml_data += '</url>\n'

    # 关闭urlset标签
    xml_data += '</urlset>\n'

    # 更新缓存数据和时间戳
    sitemap_cache['data'] = xml_data
    sitemap_cache['timestamp'] = time.time()

    return Response(xml_data, mimetype='text/xml')


# 创建全局变量来存储 feed 数据的缓存和时间戳
rss_cache = {
    'data': None,
    'timestamp': None
}


@app.route('/feed')
@app.route('/rss')
def generate_rss():
    global rss_cache

    # 检查缓存是否存在且在一个小时之内
    if (
            rss_cache['data'] is not None and
            rss_cache['timestamp'] is not None and time.time() - sitemap_cache['timestamp'] < 3600
    ):
        return Response(rss_cache['data'], mimetype='application/rss+xml')

    hidden_articles = read_hidden_articles()
    hidden_articles = [ha + ".md" for ha in hidden_articles]
    files = os.listdir('articles')
    markdown_files = [file for file in files if file.endswith('.md')]
    markdown_files = markdown_files[:10]

    # 创建XML文件头及其他信息...
    xml_data = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_data += '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
    xml_data += '<channel>\n'
    xml_data += '<title>Your RSS Feed Title</title>\n'
    xml_data += '<link>' + domain + '</link>\n'
    xml_data += '<description>Your RSS Feed Description</description>\n'
    xml_data += '<language>en-us</language>\n'
    xml_data += '<lastBuildDate>' + str(datetime.now()) + '</lastBuildDate>\n'
    xml_data += '<atom:link href="' + domain + 'rss" rel="self" type="application/rss+xml" />\n'

    for file in markdown_files:
        article_name = file[:-3]  # 移除文件扩展名 (.md)
        encoded_article_name = urllib.parse.quote(article_name)  # 对文件名进行编码处理
        article_url = domain + 'blog/' + encoded_article_name
        date = get_file_date(encoded_article_name)
        if file in hidden_articles:
            describe = "本文章属于加密文章"
            content = "本文章属于加密文章\n" + f'<a href="{article_url}" target="_blank" rel="noopener">带密码访问</a>'
        else:
            content, *_ = get_article_content(article_name, 10)
            describe = encoded_article_name

        # 创建item标签并包含内容
        xml_data += '<item>\n'
        xml_data += f'\t<title>{article_name}</title>\n'
        xml_data += f'\t<link>{article_url}</link>\n'
        xml_data += f'\t<guid>{article_url}</guid>\n'
        xml_data += f'\t<pubDate>{date}</pubDate>\n'
        xml_data += f'\t<description>{describe}</description>\n'
        xml_data += f'\t<content:encoded><![CDATA[{content}]]></content:encoded>'
        xml_data += '</item>\n'

    # 关闭channel和rss标签
    xml_data += '</channel>\n'
    xml_data += '</rss>\n'

    # 更新缓存数据和时间
    rss_cache['data'] = xml_data
    rss_cache['timestamp'] = time.time()

    return Response(xml_data, mimetype='application/rss+xml')


authorMapper = configparser.ConfigParser()


@app.route('/robots.txt')
def static_from_root():
    content = "User-agent: *\nDisallow: /admin"
    modified_content = content + '\nSitemap: ' + domain + 'sitemap.xml'  # Add your additional rule here

    response = Response(modified_content, mimetype='text/plain')
    return response


@app.route('/<path:undefined_path>')
def undefined_route(undefined_path):
    return render_template('error.html', status_code='404'), 404


#
@app.route('/hidden/article', methods=['POST'])
def hidden_article():
    article = request.json.get('article')
    if article is None:
        return jsonify({'message': '404'}), 404

    userStatus = 1
    username = 1

    if userStatus is None or username is None:
        return jsonify({'deal': 'noAuth'})

    auth = auth_articles(article, username)

    if not auth:
        return jsonify({'deal': 'noAuth'})

    if is_hidden(article):
        # 取消隐藏文章
        unhide_article(article)
        return jsonify({'deal': 'unhide'})
    else:
        # 隐藏文章
        hide_article(article)
        return jsonify({'deal': 'hide'})


def hide_article(article):
    with open('articles/hidden.txt', 'a', encoding=global_encoding) as hidden_file:
        # 将文章名写入hidden.txt的新的一行中
        hidden_file.write('\n' + article + '\n')


def unhide_article(article):
    with open('articles/hidden.txt', 'r', encoding=global_encoding) as hidden_file:
        hidden_articles = hidden_file.read().splitlines()

    with open('articles/hidden.txt', 'w', encoding=global_encoding) as hidden_file:
        # 从hidden中移除完全匹配文章名的一行
        for hidden_article in hidden_articles:
            if hidden_article != article:
                hidden_file.write(hidden_article + '\n')


def is_hidden(article):
    with open('articles/hidden.txt', 'r', encoding=global_encoding) as hidden_file:
        hidden_articles = hidden_file.read().splitlines()
        return article in hidden_articles


@app.route('/travel', methods=['GET'])
def travel():
    response = requests.get(domain + 'sitemap.xml')  # 发起对/sitemap接口的请求
    if response.status_code == 200:
        tree = ET.fromstring(response.content)  # 使用xml.etree.ElementTree解析响应内容

        urls = []  # 用于记录提取的URL列表
        for url_element in tree.findall('{http://www.sitemaps.org/schemas/sitemap/0.9}url'):
            loc_element = url_element.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
            if loc_element is not None:
                urls.append(loc_element.text)  # 将标签中的内容添加到列表中

        if urls:
            random.shuffle(urls)  # 随机打乱URL列表的顺序
            random_url = urls[0]  # 选择打乱后的第一个URL
            return render_template('bh.html', jumpUrl=random_url)
        # 如果没有找到任何<loc>标签，则返回适当的错误信息或默认页面
        return "No URLs found in the response."
    else:
        # 处理无法获取响应内容的情况，例如返回错误页面或错误消息
        return "Failed to fetch sitemap content."


def vip_blog(article_name):
    userStatus = 1
    username = 1
    auth = False  # 设置默认值

    if userStatus and username is not None:
        # Auth 认证
        auth = auth_articles(article_name, username)

    if auth:
        if request.method == 'GET':
            article_Surl = domain + 'blog/' + article_name
            article_url = "https://api.7trees.cn/qrcode/?data=" + article_Surl
            author = get_blog_author(article_name)
            blogDate = get_file_date(article_name) + '——_______该文章处于隐藏模式(他人不可见)______——'

            # 检查session中是否存在theme键
            if 'theme' not in session:
                session['theme'] = 'day-theme'  # 如果不存在，则设置默认主题为白天（day-theme）

            article_content, readNav_html = get_article_content(article_name, 215)
            article_summary = clear_html_format(article_content)
            article_summary = article_summary[:30]

            # 分页参数
            page = request.args.get('page', default=1, type=int)
            per_page = 10  # 每页显示的评论数量

            username = None
            comments = []
            if session.get('logged_in'):
                username = session.get('username')
                if username:
                    comments = None
                else:
                    comments = None
            else:
                comments = None

            if request.method == 'POST':
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(comments=comments)  # 返回JSON响应，只包含评论数据

            return render_template('zyDetail.html', article_content=article_content, articleName=article_name,
                                   theme=session['theme'], author=author, blogDate=blogDate, comments=comments,
                                   url_for=url_for, username=username, article_url=article_url,
                                   article_Surl=article_Surl, article_summary=article_summary, readNav=readNav_html,
                                   key="欢迎访问")

        elif request.method == 'POST':
            content = request.json.get('content', '')
            show_edit = zy_show_article(content)
            return jsonify({'show_edit': show_edit})
        else:
            # 渲染编辑页面
            return zy_pw_blog(article_name)
    else:
        return zy_pw_blog(article_name)


def zy_pw_blog(article_name):
    session.setdefault('theme', 'day-theme')
    if request.method == 'GET':
        # 在此处添加密码验证的逻辑
        codePass = zy_pw_check(article_name, request.args.get('password'))
        if codePass == 'success':
            try:
                # 根据文章名称获取相应的内容并处理
                article_name = article_name
                article_Surl = domain + 'blog/' + article_name
                article_url = "https://api.7trees.cn/qrcode/?data=" + article_Surl
                author = get_blog_author(article_name)
                blogDate = get_file_date(article_name) + '文章密码已认证'

                # 检查session中是否存在theme键
                if 'theme' not in session:
                    session['theme'] = 'day-theme'  # 如果不存在，则设置默认主题为白天（day-theme）

                article_content, readNav_html = get_article_content(article_name, 215)
                article_summary = clear_html_format(article_content)
                article_summary = article_summary[:30]

                # 分页参数
                page = request.args.get('page', default=1, type=int)
                per_page = 10  # 每页显示的评论数量

                username = None
                comments = []
                if session.get('logged_in'):
                    username = session.get('username')
                    if username:
                        comments = None
                    else:
                        comments = None
                else:
                    comments = None

                if request.method == 'POST':
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return jsonify(comments=comments)  # 返回JSON响应，只包含评论数据

                return render_template('zyDetail.html', article_content=article_content, articleName=article_name,
                                       theme=session['theme'], author=author, blogDate=blogDate, comments=comments,
                                       url_for=url_for, username=username, article_url=article_url,
                                       article_Surl=article_Surl, article_summary=article_summary, readNav=readNav_html,
                                       key="密码验证成功")

            except FileNotFoundError:
                return render_template('error.html', status_code='404'), 404

        else:
            return render_template('zyDetail.html', articleName=article_name,
                                   theme=session['theme'],
                                   url_for=url_for)


def zy_pw_check(article, code):
    try:
        if article and code:
            app.logger.info('完成了一次数据表更新')
        return 'success'
    except:
        return 'failed'


def get_media_list(username, category, page=1, per_page=10):
    files = []
    file_suffix = ()
    if category == 'img':
        file_suffix = ('.png', '.jpg', '.webp')
    elif category == 'video':
        file_suffix = ('.mp4', '.avi', '.mkv', '.webm', '.flv')
    file_dir = os.path.join('media', username)
    if not os.path.exists(file_dir):
        os.makedirs(file_dir)

    files = [file for file in os.listdir(file_dir) if file.endswith(tuple(file_suffix))]
    files = sorted(files, key=lambda x: os.path.getctime(os.path.join(file_dir, x)), reverse=True)
    total_img_count = len(files)
    total_pages = (total_img_count + per_page - 1) // per_page

    start_index = (page - 1) * per_page
    end_index = start_index + per_page
    files = files[start_index:end_index]

    has_next_page = page < total_pages
    has_previous_page = page > 1

    return files, has_next_page, has_previous_page


def get_all_img(username, page=1, per_page=10):
    imgs, has_next_page, has_previous_page = get_media_list(username, category='img')
    return imgs, has_next_page, has_previous_page


def get_all_video(username, page=1, per_page=10):
    videos, has_next_page, has_previous_page = get_media_list(username, category='video')
    return videos, has_next_page, has_previous_page


@app.route('/zyImg/<username>/<img_name>')
@app.route('/get_image_path/<username>/<img_name>')
def get_image_path(username, img_name):
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        img_dir = os.path.join(base_dir, 'media', username)  # 修改为实际的图片目录相对路径
        img_path = os.path.join(img_dir, img_name)  # 图片完整路径

        # 从缓存中获取图像数据
        img_data = cache.get(img_path)

        # 如果缓存中没有图像数据，则从文件中读取并进行缓存
        if img_data is None:
            with open(img_path, 'rb') as f:
                img_data = f.read()
            cache.set(img_path, img_data)

        return send_file(img_path, mimetype='image/png')
    except Exception as e:
        print(f"Error in getting image path: {e}")
        return None


@app.route('/upload_image/<username1>', methods=['POST'])
def upload_image_path(username1):
    userStatus = 1
    username = 1
    Auth = bool(username1 == username)

    if userStatus and username is not None and Auth:
        if request.method == 'POST':
            try:
                file = None
                if 'file' in request.files:
                    file = request.files['file']

                if file is not None and file.filename.lower().endswith(
                        ('.jpg', '.png', '.webp', '.jfif', '.pjpeg', '.jpeg', '.pjp')):
                    if file.content_length > 10 * 1024 * 1024:
                        return 'Too large please use a file smaller than 10MB'
                    else:
                        if file:
                            img_dir = os.path.join('media', username)
                            os.makedirs(img_dir, exist_ok=True)

                            file_path = os.path.join(img_dir, file.filename)

                            with open(file_path, 'wb') as f:
                                f.write(file.read())

                            return 'success'
                else:
                    return 'Invalid file format. Only image files are allowed.'
            except Exception as e:
                print(f"Error in getting image path: {e}")
                return 'failed'
    else:
        return 'failed'


@app.route('/zyVideo/<username>/<video_name>')
def start_video(username, video_name):
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        video_dir = os.path.join(base_dir, 'media', username)
        video_path = os.path.join(video_dir, video_name)

        return send_file(video_path, mimetype='video/mp4', as_attachment=False, conditional=True)
    except Exception as e:
        print(f"Error in getting video path: {e}")
        return None


@app.route('/jump', methods=['GET', 'POST'])
def jump():
    url = request.args.get('url', default=domain)
    return render_template('zyJump.html', url=url, domain=domain)


@app.route('/static/<path:filename>')
def serve_static(filename):
    parts = filename.split('/')
    directory = safe_join('/'.join(parts[:-1]))
    file = parts[-1]
    return send_from_directory(directory, file)
