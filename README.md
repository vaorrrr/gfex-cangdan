# 广期所仓单日报

每日自动展示广州期货交易所 **多晶硅、工业硅、碳酸锂** 的标准仓单数据：

- 注册量
- 注销量
- 净变化量
- 今日 / 昨日仓单总量
- 各仓库明细

数据来源： [广期所官方仓单日报](http://www.gfex.com.cn/gfex/cdrb/hqsj_tjsj.shtml)

---

## 一、部署成在线网址（推荐，手机随时打开 + 自动更新）

### 第 1 步：注册 / 登录 GitHub
打开 [https://github.com](https://github.com) ，没有账号就注册一个（免费）。

### 第 2 步：新建仓库
1. 点击右上角 **+** → **New repository**
2. Repository name 填写：`gfex-cangdan`（或任意英文名）
3. 选择 **Public**
4. **不要**勾选 “Add a README file”
5. 点击 **Create repository**

### 第 3 步：上传文件
1. 在新仓库页面，点击 **uploading an existing file**
2. 把本文件夹里的所有内容拖进去（包括 `.github` 文件夹）
3. 点击底部绿色按钮 **Commit changes**

> 注意：必须把 `.github` 文件夹也上传进去，否则无法自动更新。

### 第 4 步：开启 GitHub Pages
1. 进入仓库的 **Settings**（设置）
2. 左侧找到 **Pages**
3. Source 选择 **Deploy from a branch**
4. Branch 选 `main`（或 `master`），文件夹选 `/ (root)`
5. 点击 **Save**

等待大约 1～2 分钟，页面会显示你的网址，类似：

```
https://你的用户名.github.io/gfex-cangdan/
```

这个网址就是可以分享给任何人、手机随时打开的在线地址。

### 第 5 步：开启自动更新（重要）
1. 进入仓库的 **Actions** 标签页
2. 如果提示开启 Workflow，点击 **I understand my workflows, go ahead and enable them**
3. 之后每天北京时间约 17:45 会自动运行一次，更新当天仓单数据

也可以随时在 Actions 页面手动点击 **Run workflow** 立即更新。

---

## 二、本地使用

```bash
# 更新数据
python3 update_data.py

# 本地预览
python3 -m http.server 8080
```

然后浏览器打开 http://localhost:8080

---

## 文件说明

| 文件 | 说明 |
|------|------|
| `index.html` | 网站页面 |
| `data.json` | 最新仓单数据 |
| `update_data.py` | 数据更新脚本 |
| `.github/workflows/update.yml` | GitHub 自动更新配置 |

---

## 注意事项

- 非交易日可能无新数据，脚本会自动使用最近一个有数据的交易日
- 广期所数据通常在收盘后（15:00 后）陆续发布，建议 17:30 之后再更新
- 本项目仅做数据展示，不构成任何投资建议
