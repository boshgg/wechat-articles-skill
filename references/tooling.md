# 工具用法与限制

脚本只处理本地文件，不执行联网核查、不替用户完成语义审查。`build` 要求独立审查记录，但不把“文件存在”当成审查正确的证据。

## 环境

在 Codex 中先用 workspace dependency loader 查找打包的 Python/Node/Pillow/python-docx/lxml/Playwright 路径，按实际返回值调用。不要把本机 Administrator 缓存版本写成可移植硬依赖。独立使用时可在隔离环境安装 `requirements.txt`；浏览器 QA 需要另行提供 Playwright 与 Chrome/Chromium。

以下命令里的 `python`/`node` 表示已经定位的运行时，不要求是系统程序。Windows 中文路径使用正确引号，必要时设置 `PYTHONIOENCODING=utf-8`。

## 提取

```powershell
python scripts/article_tool.py extract "E:/公众号文章/未修改Word/作者：姓名/新稿.docx" --out "E:/公众号文章/_work/qa/本次稿件/source"
```

输出 `source.json` 和 `media/`。记录原稿哈希、正文块顺序、样式/加粗/编号提示、表格行列、实际引用图片及未引用媒体。它不是完整 Word 排版解析器：合并/嵌套表、文本框、脚注、修订、图表、SmartArt、公式、外链图、表格内图、AlternateContent 备用表示会发出警告，常规 build 拒绝此类输入。需用 Word/OOXML 的专门保真方式处理，并人工验证全部内容；不能删掉警告骗过关卡。

老 `.doc` 必须先用可用 Word/WPS 或合适转换器另存副本为 `.docx`，不覆盖原稿、不仅改扩展名。转换后核对原稿文字和全部图片；纯文本应急提取不能冒充完整转换。扫描型文章/OLE 特殊素材同样需要单独处理并报告限制。

## 审查、Markdown 与生成

按照审查规则处理正文，将原图复制到 `Markdown/assets/<唯一文章目录>/` 并验证字节不变，Markdown 用相对路径引用。`source.json` 保留在 QA 目录。

工具支持受控 Markdown 子集：一个 H1、H2-H4、独立段落、成对加粗、HTTP(S)链接、独立图像行、引用、顺序列表、简单矩形管道表。要点每项空一行；普通 `- ` 要点将生成独立段落。复杂嵌套 Markdown、脚注、内联 HTML、公式、转义管道和合并表格需要专门渲染，不应静默交给该解析器。

日期/原标题/作者必须人工确认后写成标准文件名。追加 `assets/company-closing.md`，在 `审查记录` 另存真实审查记录。

```powershell
python scripts/article_tool.py build "E:/公众号文章/Markdown/2026.09.07原标题（修改后）姓名.md" --workspace "E:/公众号文章" --snapshot "E:/公众号文章/_work/qa/本次稿件/source/source.json" --audit "E:/公众号文章/审查记录/本次稿件.md"
```

build 生成 Word、HTML 和 `_work/qa/<文章文件名>/build.json`，对已有输出默认报错。先比对归属、源版本与用户修改后才可加 `--replace`。Markdown 是已审查的输入，不会被脚本自动纠错；三种格式完成后仍须进行语义与视觉验收。

默认始终保留可见原标题；仅在人工查看原封面并确认已有完整标题、在审查记录说明后，才可传 `--cover-has-title` 避免重复。仅有“封面”替代文本不是依据。

正文原本在讨论“待核实”等状态词时，人工判断后可以 `--literal-text "原 Word 中含该词的完整上下文句子"` 精确放行，多个句子重复传参。句子必须至少 10 个字符且真实出现在提取原文中，并将判断记入独立审查记录；不得用来放行新增的编辑意见。真实标题中的 C++ 等字面加号可以保留，字段连接用的加号仍应删除。

`_build_wechat_html.py`、`_build_reviewed_docs.py` 是底层生成器，支持显式 `--output-dir`，不带审查门槛和备份。常规使用优先入口 article_tool，直接用底层时必须人工执行同等验收，不应当作绕过检查的方法。

## 检查

```powershell
python scripts/article_tool.py verify "E:/公众号文章/_work/qa/文章文件名/build.json"
node scripts/qa_html.mjs --out "E:/公众号文章/_work/qa/本次稿件/browser" "E:/公众号文章/html文章/2026.09.07原标题（修改后）姓名.html"
```

Playwright 模块不在默认搜索路径时，设置 `PLAYWRIGHT_MODULE` 为实际模块入口绝对路径；`PLAYWRIGHT_CHANNEL` 可指定已安装浏览器，默认 chrome。控制超时后按用户要求使用可用 Computer Use，不反复修复 Chrome。截图必须打开查看，不能只读 pass 数字。

verify 对照提取清单与成稿，核验源文件和各格式哈希、文本顺序、图片真实解码字节及重复次数、表格数量和结尾。其文本检查以审查后 Markdown 为基准；原文到 Markdown 的必要修改与完整性仍由代理逐项审阅。若最终文件有变，重建清单并重做 QA，不篡改哈希掩盖变更。

## 备份

```powershell
python scripts/article_tool.py backup "E:/公众号文章/_work/qa/文章文件名/build.json"
```

默认目标为配置中的指定共享目录。测试或迁移使用 `--destination` 显式改变目标；不同内容同名拒绝覆盖，确认后才能 `--replace`。相同内容幂等跳过。命令重新读取副本哈希并更新 build.json；网络失败保留本地成稿，报告未完成。

## 回归测试

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python tests/create_demo.py --out "临时QA目录"
```

测试只生成合成材料，不使用或上传真实原稿。生成 demo 后按返回的 HTML、Word 路径完成浏览器及 Word 渲染检查。仓库的 `.gitignore` 排除文档、QA、数据库、凭据等，上传前仍须审查 Git 暂存清单。
