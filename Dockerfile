# 使用基础镜像
FROM python:3.12.4

# 设置工作目录
WORKDIR /app

# 仅复制requirements.txt并安装依赖
COPY requirements.txt /app/
RUN pip install -r requirements.txt

# 复制应用程序代码
COPY . /app

# 暴露端口
EXPOSE 9876

# 设置环境变量
# 注意DOMAIN格式,以斜杠结尾
# BLOG_TITLE(您的网站名称)
ENV DOMAIN='http://127.0.0.1:9876/'
ENV BLOG_TITLE='七棵树'
ENV PORT=9876

# 定义启动命令
CMD ["python", "wsgi.py"]
