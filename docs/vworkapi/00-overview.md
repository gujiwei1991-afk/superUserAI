# vworkApi 文档归档（本地缓存）

> 来源: https://www.showdoc.com.cn/mrsanshui/10976057765422043 
> 抓取时间: 见 git 提交;后续接口字段如有改动请重新抓取。

## 章节速查

- [1、基础功能](./01-basic.md)
- [2、好友/群/成员/公司/部门 列表](./02-list.md)
- [3、发送消息](./03-send.md)
- [4、好友操作](./04-friend.md)
- [5、群操作](./05-group.md)
- [6、标签操作](./06-tag.md)
- [7、控制类](./07-control.md)
- [8、开放平台](./08-open-platform.md)
- [9、CDN 上下载](./09-cdn.md)
- [10、其他](./10-misc.md)
- [消息推送（DLL 主动请求你的）](./11-recv.md)

## 关键决策（本项目）

- **入站消息字段判定**(见 `11-recv.md` → 聊天消息):
  - `sender != ''` ⇒ 群消息(此时 `user_id` 是群 ID,`sender` 是发送者 ID)
  - `sender == ''` ⇒ 私聊(此时 `user_id` 就是发送者 ID)
  - `self_user_id in at_list` 或 `'notify@all' in at_list` ⇒ 被 @ 到
- **发送文本到群**: 直接用 `type=3000` SEND_TEXT,`user_id=群ID`(见 `03-send.md` → 发送文本消息)
- **发送 @ 群成员**: `type=3009` SEND_AT_GROUP,字段 `chat_room_id`/`at_list`/`msg`(见 `03-send.md` → 群聊发送消息并且@指定群成员)

## 顶层说明

### 说明

**介绍**

- 《vworkApi》是基于PC端的企业微信封装的、REST风格的接口，开发者可通过**HTTP轻松调用**。可进行二次开发，实现微信机器人、群管理等强大的功能！

# 社区版跟专业版的区别？
- 社区版：
	- 麻雀虽小五脏俱全！
	- 不支持长时间运行
	- 不再维护更新
	- 微信版本：4.0.0.6024
- 专业版：
	- 功能更加强大、稳定！
	- 支持长时间运行
	- 使用有保障！持续更新迭代
	- 微信版本：5.0.3.6005

> <span style="color: red">功能区别请打开《社区版跟专业版的区别》进行查看</span>

## 使用教程（仅需3步）
> <span style="color: #ff5050">使用前请先安装指定版本的微信</span>
> 指定版本微信安装包：[https://pan.baidu.com/s/1FKlfwVsFLOhAKYlpSWSSMA](https://pan.baidu.com/s/1FKlfwVsFLOhAKYlpSWSSMA "https://pan.baidu.com/s/1FKlfwVsFLOhAKYlpSWSSMA")
> 提取码：sszs

1. 运行《注入工具(图形界面版).exe》点击启动并注入
2. 监听消息：开启一个HTTP服务，并且运行在 `9000` 端口上，请求路径为 `/msg`，请求方法为 `POST`
3. 操作接口：注入成功后，即可向 `8989` 端口发送HTTP请求，执行对应操作，请求路径为 `/api`，请求方法为 `POST`

## 更灵活的使用方法（使用命令行注入）
如需更灵活的使用，可使用命令行调用《inject_tool.exe》

命令参数：[inject_tool.exe的全路径] start [DLL的端口号]

示例：`C:\inject_tool.exe start 8989 --my_port=9000`

<span style="color: red">注意：</span>`--my_port` 就是你用来接收消息的端口号，这个参数是可选的，不填的话默认就是9000

## 如何多开？
非常简单！
不论你是使用《图形界面工具注入》、还是《命令行注入》
都只需要输入不同的 `[DLL的端口号]` 即可实现多开

- 第1个号：`C:\inject_tool.exe start 8989`
- 第2个号：`C:\inject_tool.exe start 8990`
- 第3个号：`C:\inject_tool.exe start 8991`
- 以此类推...

## 如何指定exe的路径？
命令行参数：`--exe_path=exe的绝对路径`

## 声明
**本项目仅供技术研究，请勿用于非法用途，如有任何人凭此做何非法事情，均于作者无关，特此声明。**

---

### 社区版跟专业版的区别

| 功能 | 社区版 | 专业版 |
|:---: |:---: |:---: |
| 微信版本 | 4.0.0.6024 | 5.0.3.6005 |
| 微信多开 | 支持 | 支持 |
| 获取登录状态 | 支持 | 支持 |
| 刷新并获取登录二维码 | 支持 | 支持 |
| 获取个人信息 | 支持 | 支持 |
| 退出登录 | 支持 | 支持 |
| 获取个人二维码 | <span style="color: #ff5050">不支持</span> | 支持 |
| 获取好友列表【外部】 | 支持 | 支持 |
| 获取好友列表【内部】 | 支持 | 支持 |
| 获取群列表 | 支持 | 支持 |
| 获取群成员列表 | 支持 | 支持 |
| 获取公司列表 | <span style="color: #ff5050">不支持</span> | 支持 |
| 获取部门列表 | <span style="color: #ff5050">不支持</span> | 支持 |
| 发送文本消息 | 支持 | 支持 |
| 发送图片消息 | <span style="color: #ff5050">不支持</span> | 支持 |
| 发送GIF表情 | <span style="color: #ff5050">不支持</span> | 支持 |
| 发送文件消息 | <span style="color: #ff5050">不支持</span> | 支持 |
| 发送视频消息 | <span style="color: #ff5050">不支持</span> | 支持 |
| 发送名片 | <span style="color: #ff5050">不支持</span> | 支持 |
| 发送小程序 | <span style="color: #ff5050">不支持</span> | 支持 |
| 发送视频号 | <span style="color: #ff5050">不支持</span> | 支持 |
| 发送卡片链接 | <span style="color: #ff5050">不支持</span> | 支持 |
| 群聊发送消息并且@指定群成员 | <span style="color: #ff5050">不支持</span> | 支持 |
| 发送位置消息 | <span style="color: #ff5050">不支持</span> | 支持 |
| 发送语音消息 | <span style="color: #ff5050">不支持</span> | 支持 |
| 发送图片消息【CDN方式】 | <span style="color: #ff5050">不支持</span> | 支持 |
| 发送视频消息【CDN方式】 | <span style="color: #ff5050">不支持</span> | 支持 |
| 发送文件消息【CDN方式】 | <span style="color: #ff5050">不支持</span> | 支持 |
| 添加好友【群成员】 | <span style="color: #ff5050">不支持</span> | 支持 |
| 添加好友【网络查询】 | <span style="color: #ff5050">不支持</span> | 支持 |
| 删除好友 | <span style="color: #ff5050">不支持</span> | 支持 |
| 同意好友请求 | <span style="color: #ff5050">不支持</span> | 支持 |
| 设置好友备注 | <span style="color: #ff5050">不支持</span> | 支持 |
| 设置好友描述 | <span style="color: #ff5050">不支持</span> | 支持 |
| 设置好友公司 | <span style="color: #ff5050">不支持</span> | 支持 |
| 设置好友手机号 | <span style="color: #ff5050">不支持</span> | 支持 |
| 本地查询好友信息 | <span style="color: #ff5050">不支持</span> | 支持 |
| 网络查询陌生人信息 | <span style="color: #ff5050">不支持</span> | 支持 |
| 创建群聊【外部】 | <span style="color: #ff5050">不支持</span> | 支持 |
| 创建群聊【内部】 | <span style="color: #ff5050">不支持</span> | 支持 |
| 修改群名称 | <span style="color: #ff5050">不支持</span> | 支持 |
| 发送群公告 | <span style="color: #ff5050">不支持</span> | 支持 |
| 邀请好友进群（40人以下） | <span style="color: #ff5050">不支持</span> | 支持 |
| 邀请好友进群（40人以上） | <span style="color: #ff5050">不支持</span> | 支持 |
| 删除群成员 | <span style="color: #ff5050">不支持</span> | 支持 |
| 获取群二维码 | <span style="color: #ff5050">不支持</span> | 支持 |
| 获取群信息 | <span style="color: #ff5050">不支持</span> | 支持 |
| 获取欢迎语列表 | <span style="color: #ff5050">不支持</span> | 支持 |
| 添加欢迎语 | <span style="color: #ff5050">不支持</span> | 支持 |
| 设置欢迎语 | <span style="color: #ff5050">不支持</span> | 支持 |
| 移除欢迎语 | <span style="color: #ff5050">不支持</span> | 支持 |
| 添加管理员 | <span style="color: #ff5050">不支持</span> | 支持 |
| 删除管理员 | <span style="color: #ff5050">不支持</span> | 支持 |
| 转让群主 | <span style="color: #ff5050">不支持</span> | 支持 |
| 退出群聊 | <span style="color: #ff5050">不支持</span> | 支持 |
| 解散群聊 | <span style="color: #ff5050">不支持</span> | 支持 |
| 允许/禁止修改群名 | <span style="color: #ff5050">不支持</span> | 支持 |
| 开启/关闭邀请确认 | <span style="color: #ff5050">不支持</span> | 支持 |
| 获取标签组列表 | <span style="color: #ff5050">不支持</span> | 支持 |
| 添加标签 | <span style="color: #ff5050">不支持</span> | 支持 |
| 修改标签 | <span style="color: #ff5050">不支持</span> | 支持 |
| 删除标签 | <span style="color: #ff5050">不支持</span> | 支持 |
| 一个好友打多个标签 | <span style="color: #ff5050">不支持</span> | 支持 |
| 一个标签打多个好友 | <span style="color: #ff5050">不支持</span> | 支持 |
| 获取标签下的联系人 | <span style="color: #ff5050">不支持</span> | 支持 |
| 删除标签下的联系人 | <span style="color: #ff5050">不支持</span> | 支持 |
| 开启/关闭自动更新 | <span style="color: #ff5050">不支持</span> | 支持 |
| 开启/关闭自动登录 | <span style="color: #ff5050">不支持</span> | 支持 |
| 开启/关闭消息免打扰 | <span style="color: #ff5050">不支持</span> | 支持 |
| 开启/关闭自动下载 | <span style="color: #ff5050">不支持</span> | 支持 |
| 企业用户ID转开放平台ID | <span style="color: #ff5050">不支持</span> | 支持 |
| 企业群ID转开放平台ID | <span style="color: #ff5050">不支持</span> | 支持 |
| 开放平台ID转企业用户ID | <span style="color: #ff5050">不支持</span> | 支持 |
| 开放平台ID转企业群ID | <span style="color: #ff5050">不支持</span> | 支持 |
| CDN上传图片 | <span style="color: #ff5050">不支持</span> | 支持 |
| CDN上传视频 | <span style="color: #ff5050">不支持</span> | 支持 |
| CDN上传文件 | <span style="color: #ff5050">不支持</span> | 支持 |
| CDN下载图片 | <span style="color: #ff5050">不支持</span> | 支持 |
| CDN下载视频 | <span style="color: #ff5050">不支持</span> | 支持 |
| CDN下载文件 | <span style="color: #ff5050">不支持</span> | 支持 |
| CDN下载个微图片/视频/文件 | <span style="color: #ff5050">不支持</span> | 支持 |
| 清空聊天记录 | <span style="color: #ff5050">不支持</span> | 支持 |
| 语音转文字 | <span style="color: #ff5050">不支持</span> | 支持 |
| 获取当前微信进程的PID | <span style="color: #ff5050">不支持</span> | 支持 |
| 获取当前聊天窗口信息 | <span style="color: #ff5050">不支持</span> | 支持 |
| 监听聊天消息 | 支持 | 支持 |
| 好友申请通知 | <span style="color: #ff5050">不支持</span> | 支持 |
| 删除好友通知 | <span style="color: #ff5050">不支持</span> | 支持 |
| 群昵称变动通知 | <span style="color: #ff5050">不支持</span> | 支持 |
| 退出登录通知 | <span style="color: #ff5050">不支持</span> | 支持 |
| 系统弹窗通知 | <span style="color: #ff5050">不支持</span> | 支持 |
| 输入登录验证码通知 | <span style="color: #ff5050">不支持</span> | 支持 |
| 输入登录验证码 | <span style="color: #ff5050">不支持</span> | 支持 |
| 长时间运行 | <span style="color: #ff5050">不支持</span> | 支持 |
| 迭代更新 | <span style="color: #ff5050">不在更新维护</span> | 持续迭代更新 |

---

