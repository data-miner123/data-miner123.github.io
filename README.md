# data-miner123.github.io
关于修改数据更新
服务器更新至GitHub：

(1)修改不需要重启网站的文件：
```
先检查修改 
git status 
git diff -- 文件名（含后缀）
```
内容正确后提交：
```
git add 文件名（含后缀）
git commit -m “Update 文件名（无后缀）”
```

同步其他成员可能已经提交的内容： ```git pull --rebase origin main ```
最后上传到 GitHub： ```git push origin main  ```

exp： ```cd ~/VIS_Group```
```
git add README.md
git commit -m "Update README"
git pull --rebase origin main
git push origin main
```
(2)修改需要重启的文件，例如：
server.py
在服务器修改并保存 server.py 后，按以下顺序操作。

先检查 Python 语法：
```
cd ~/VIS_Group
/usr/local/anaconda3/bin/python3 -m py_compile server.py
```

没有输出表示语法检查通过。
然后提交并推送 GitHub：
```
git status
git diff -- server.py
git add server.py
git commit -m "Update server"
git pull --rebase origin main
git push origin main
```

再切换到系统管理员账号：
```su - ren9000k （jsklren9000k）```
重启并检查网站：
```
sudo systemctl restart vis-group
sudo systemctl status vis-group --no-pager
```
应显示：
```Active: active (running)```
再测试接口：
```
curl -s -o /dev/null -w "HTTP状态码：%{http_code}\n" \
http://127.0.0.1:8000/api/site
```
返回 200 表示正常。若启动失败，查看日志：
```sudo journalctl -u vis-group -n 50 --no-pager```
不同文件的处理方式：

| 修改文件 | 是否需要重启网站 | 说明 |
|---|---|---|
| `server.py` | 需要 | Python 后端程序 |
| `static/index.html` | 通常不需要 | 刷新浏览器即可 |
| `static/styles.css` | 不需要 | 强制刷新浏览器 |
| `static/app.js` | 通常不需要 | 强制刷新浏览器 |
| 根目录 `index.html` | 不需要 | GitHub Pages 页面 |
| 根目录 `landing.css` | 不需要 | GitHub Pages 样式 |
| `README.md` | 不需要 | 项目说明文档 |
修改静态文件后如果页面还是旧版本，使用 Cmd+Shift+R 强制刷新。

GitHub更新至服务器： 无需操作，每五分钟自动更新同步 
