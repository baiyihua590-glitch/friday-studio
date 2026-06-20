#!/bin/bash
# 星期五Studio - PythonAnywhere 部署脚本

# 1. 修改 WSGI 文件
cat > /var/www/baiyihua590_pythonanywhere_com_wsgi.py << 'EOF'
import sys
sys.path.insert(0, '/home/baiyihua590')
from backend import app as application
EOF

# 2. 重载 Web 应用
echo "WSGI 配置文件已更新，请到 Web 页面点击 Reload"
