from src.app import app
import os

def main():
    """
    Main function to start the server.
    """
    # 运行生成文件代码
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 80)))

if __name__ == '__main__':
    main()