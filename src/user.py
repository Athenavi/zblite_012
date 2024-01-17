import os
from configparser import ConfigParser

from flask import render_template

config = ConfigParser()
config.read('config.ini', encoding='utf-8')


def error(message, status_code):
    return render_template('error.html', error=message, status_code=status_code), status_code


def read_hidden_articles():
    hidden_articles = []
    with open('articles/hidden.txt', 'r') as hidden_file:
        hidden_articles = hidden_file.read().splitlines()
    return hidden_articles



def show_files(path):
    # 指定目录的路径
    directory = path
    files = os.listdir(directory)
    return files


def zy_delete_file(filename):
    # 指定目录的路径
    directory = 'articles/'

    mapper = 'author/mapper.ini'
    lines = []
    with open(mapper, 'r', encoding='utf-8') as file:
        for line in file:
            if not line.strip().startswith(filename + '='):
                lines.append(line)

    with open(mapper, 'w', encoding='utf-8') as file:
        file.writelines(lines)

    filename = filename + '.md'
    # 构建文件的完整路径
    file_path = os.path.join(directory, filename)

    try:
        # 删除文件
        os.remove(file_path)

        return 'success'

    except OSError as error:
        # 处理出错的情况
        return 'failed: ' + str(error)


def get_owner_articles(owner_name):
    articles = []

    # 读取mapper.ini文件内容
    with open('author/mapper.ini', 'r', encoding='utf-8') as file:
        lines = file.readlines()

    # 根据name获取拥有者的文章列表
    for line in lines:
        line = line.strip()
        if line and '=' in line:  # 修改这行代码
            article_info = line.split('=')
            if len(article_info) == 2:
                article_name = article_info[0].strip()
                article_owner = article_info[1].strip().strip('\'')
                if article_owner == owner_name:
                    articles.append(article_name)

    return articles
