# 消息推送（DLL 主动请求你的）

> 来源: showdoc.com.cn/mrsanshui (cat_id=5561955)

## 聊天消息

页面 ID: `10976102041752928` · 链接: https://www.showdoc.com.cn/mrsanshui/10976102041752928

**简要描述：**

- 监听聊天消息【需要自己开一个HTTP服务，DLL会主动请求你，并把消息内容推送到约定接口】

**请求URL：**

- `http://127.0.0.1:9000/msg`

**请求方式：**

- POST

**消息示例：**

```json
{
	"type": 100, // 推送类型，固定为100
	"msg_type": 2, //消息类型
	"msg_id": "10018000", //消息ID
	"user_id": "7881300000", //聊天用户ID/群ID,
	"waiter_id": "2580800000", //客服ID
	"at_list": ["7881300001", "7881300002"], // 群消息艾特人列表，艾特所有人就是【notify@all】
	"content": "不同类型的消息，该字段的值也不相同，具体看下方文档", //消息内容【可变字段】
	"sender": "7881300003", //如果是群消息，该参数为发送者的用户ID，否则为空
	"time_stamp": 1682944354, //发送时间
	"is_self_msg": 1, //是否是自己发送的消息 0:别人发来的 1:自己发的
	"is_pc_msg": 1, //是否是PC端发送的消息(仅用于判断自己发送的消息，别人发送的都是0) 0:否 1:是
	"self_user_id": "168888888888", //自己的用户ID
	"port": 8989 //DLL的端口号
}
```

**消息类型说明【msg_type】：**

| 消息类型 | 说明 |
| :------------: | :------------: |
| 2 | 文本消息 |
| 14 | 图片消息 |
| 29 | GIF消息 |
| 15 | 文件消息 |
| 23 | 视频消息 |
| 41 | 名片消息 |
| 78 | 小程序消息 |
| 141 | 视频号消息 |
| 13 | 卡片链接消息 |
| 6 | 位置消息 |
| 16 | 语音消息 |
| 4 | 合并消息 |
| 其他不常见的消息可根据 msg_type 自行分析 | 未知消息 |

**【2】文本消息的content：**

```json
"就是字符串"
```

**【14】图片消息的content：**

```json
{
	"cdn_key": "30520201000xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
	"aes_key": "ba8221xxxxxxxxxxxxxxxxxxxxxxxxxx",
	"url": "",
	"auth_key": "",
	"md5": "e12f93xxxxxxxxxxxxxxxxxxxxxxxxxx",
	"size": 230192, //图片大小
	"img_type": 2, //1=原图 2=高清图 3=缩略图
    "source_type": 2 //资源来源 1:个微 2:企微
}
```

**【29】GIF消息的content：**

```json
{
    "source_type": 2, //资源来源 1:个微 2:企微
    "url": "http://p.qpic.cn/pic_wework/xxx/xxx/0"
}
```

**【15】文件消息的content：**

```json
{
    "cdn_key": "30520201000xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
	"aes_key": "ba8221xxxxxxxxxxxxxxxxxxxxxxxxxx",
	"url": "",
	"auth_key": "",
	"md5": "e12f93xxxxxxxxxxxxxxxxxxxxxxxxxx",
    "size": 20308, //文件大小
	"file_name": "xxx.exe", //文件名
    "source_type": 2 //资源来源 1:个微 2:企微
}
```

**【23】视频消息的content：**

```json
{
    "cdn_key": "30520201000xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
	"aes_key": "ba8221xxxxxxxxxxxxxxxxxxxxxxxxxx",
	"url": "",
	"auth_key": "",
	"md5": "e12f93xxxxxxxxxxxxxxxxxxxxxxxxxx",
    "size": 887690, //视频大小
    "source_type": 2 //资源来源 1:个微 2:企微
}
```

**【41】名片消息的content：**

```json
{
	"corp_id": "197xxx", //公司ID
	"user_id": "168xxx", //用户ID
    "avatar_url": "https://thirdwx.qlogo.cn/mmopen/vi_32/xxx/0", //头像地址
    "nick_name": "三水君", //昵称
    "title": "超人俱乐部" //卡片标题
}
```

**【78】小程序消息的content：**

```json
{
    "app_id": "wx32540bd863b27570", //小程序ID
	"app_name": "拼夕夕", //小程序名称
	"title": "快帮我砍一刀~", //标题
	"desc": "拼单尽享优惠", //描述信息
	"wechat_id": "gh_0e7477744313@app", //微信ID
	"page_path": "pages/index/index.html?xxx", //页面路径
    "avatar_url": "http://mmbiz.qpic.cn/mmbiz_png/xxx/640?wx_fmt=png&wxfrom=200", //头像地址
    "cover_cdn_key": "30520201000xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
	"cover_aes_key": "ba8221xxxxxxxxxxxxxxxxxxxxxxxxxx",
	"cover_md5": "e12f93xxxxxxxxxxxxxxxxxxxxxxxxxx",
    "cover_size": 887690, //封面文件大小
}
```

**【141】视频号消息的content：**

```json
{
    "avatar_url": "https://wx.qlogo.cn/finderhead/ver_1/xxx/0", //头像地址
    "cover_url": "http://wxapp.tc.qq.com/251/20304/stodownload?xxx", //封面地址
	"video_url": "https://channels.weixin.qq.com/web/pages/feed?eid=xxx", //视频地址
    "desc": "KOC运营效果差？关键做好这两点#企业微信", //描述信息
    "extras": "CAEQACKxHAAE9Omxxx", //未知字符串
    "nick_name": "企业微信拍了拍你", //昵称
    "thumb_url": "http://wxapp.tc.qq.com/251/20304/stodownload?xxxxx" //缩略图地址
}
```

**【13】卡片链接消息的content：**

```json
{
	"title": "我是标题", //标题
	"desc": "我是描述信息", //描述信息
    "cover_url": "http://img.xxx.com/imgextra/i2/1031524252/xxx.jpg", //封面地址
    "target_url": "https://www.baidu.com" //目标地址
}
```

**【6】位置消息的content：**

```json
{
    "address": "北极", //地址
    "detail_address": "一块冰面上", //详细地址
    "lat": "0.000000", //纬度
    "lon": "90.000000" //经度
}
```

**【16】语音消息的content：**

```json
{
    "cdn_key": "30520201000xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
	"aes_key": "ba8221xxxxxxxxxxxxxxxxxxxxxxxxxx",
	"md5": "e12f93xxxxxxxxxxxxxxxxxxxxxxxxxx",
    "size": 3997, //语音文件大小
    "voice_time": 3 //语音时长
}
```

---

## 好友申请通知

页面 ID: `10976102510897230` · 链接: https://www.showdoc.com.cn/mrsanshui/10976102510897230

**简要描述：**

- 好友申请通知【需要自己开一个HTTP服务，DLL会主动请求你，并把消息内容推送到约定接口】
- 客户申请添加你为好友时，会推送该通知

**请求URL：**

- `http://127.0.0.1:9000/msg`

**请求方式：**

- POST

**消息示例：**

```json
{
	"type": 200, //推送类型，固定为200
	"add_source": 4, //添加来源
	"source_chat_room_id": "R:1095700000", //来源群ID
	"invite_user_id": "0", //邀请人的用户ID
	"msg": "我是三水君", //打招呼消息
	"user_id": "788130000000", //用户ID
	"corp_id": "197000000000", //公司ID
	"nick_name": "三水君", //昵称
	"avatar_url": "http://wx.qlogo.cn/mmhead/xxx/0", //头像地址
	"sex": 1, //性别
	"mobile": "1380000000", //手机号
	"self_user_id": "16888000000", //自己的用户ID
	"port": 8989 //DLL的端口号
}
```

---

## 删除好友通知

页面 ID: `10976103440974489` · 链接: https://www.showdoc.com.cn/mrsanshui/10976103440974489

**简要描述：**

- 删除好友通知【需要自己开一个HTTP服务，DLL会主动请求你，并把消息内容推送到约定接口】

**请求URL：**

- `http://127.0.0.1:9000/msg`

**请求方式：**

- POST

**消息示例：**

```json
{
	"type": 201, //推送类型，固定为201
	"del_type": 0, //删除类型 0:别人删我 1:我删别人
	"user_id": "78813000000", //用户ID
	"corp_id": "19703000000", //公司ID
	"nick_name": "三水君", //昵称
	"avatar_url": "http://wx.qlogo.cn/mmhead/xxx/0", //头像地址
	"sex": 1, //性别
	"self_user_id": "16888000000", //自己的用户ID
	"port": 8989 //DLL的端口号
}
```

---

## 群名称变动通知

页面 ID: `10976103649840726` · 链接: https://www.showdoc.com.cn/mrsanshui/10976103649840726

**简要描述：**

- 群名称变动通知【需要自己开一个HTTP服务，DLL会主动请求你，并把消息内容推送到约定接口】

**请求URL：**

- `http://127.0.0.1:9000/msg`

**请求方式：**

- POST

**消息示例：**

```json
{
	"type": 300, //推送类型，固定为300
    "chat_room_id": "R:10957714713827828", //群ID
    "new_name": "测试外部群2", //新的群名
	"user_id": "1688855305496583", //修改者的用户ID
	"self_user_id": "16888000000", //自己的用户ID
	"port": 8989 //DLL的端口号
}
```

---

## 退出登录通知

页面 ID: `10976104250458371` · 链接: https://www.showdoc.com.cn/mrsanshui/10976104250458371

**简要描述：**

- 退出登录通知【需要自己开一个HTTP服务，DLL会主动请求你，并把消息内容推送到约定接口】

**请求URL：**

- `http://127.0.0.1:9000/msg`

**请求方式：**

- POST

**消息示例：**

```json
{
	"type": 900, //推送类型，固定为900
	"msg": "你已退出登录", //提示内容
	"user_id": "16888000000", //用户ID
	"port": 8989 //DLL的端口号
}
```

---

## 系统弹窗通知

页面 ID: `10976104684242696` · 链接: https://www.showdoc.com.cn/mrsanshui/10976104684242696

**简要描述：**

- 系统弹窗通知【需要自己开一个HTTP服务，DLL会主动请求你，并把消息内容推送到约定接口】

**请求URL：**

- `http://127.0.0.1:9000/msg`

**请求方式：**

- POST

**消息示例：**

```json
{
	"type": 1000, //推送类型，固定为1000
	"title": "该用户不存在", //弹窗标题
    "msg": "无法找到该用户，请检查你填写的信息是否正确", //弹窗内容
    "self_user_id": "16888000000", //用户ID
	"port": 8989 //DLL的端口号
}
```

---

## 输入登录验证码通知

页面 ID: `11115908146135595` · 链接: https://www.showdoc.com.cn/mrsanshui/11115908146135595

**简要描述：**

- 退出登录通知【需要自己开一个HTTP服务，DLL会主动请求你，并把消息内容推送到约定接口】

**请求URL：**

- `http://127.0.0.1:9000/msg`

**请求方式：**

- POST

**消息示例：**

```json
{
	"type": 901, //推送类型，固定为901
	"msg": "请输入登录验证码", //提示内容
	"port": 8989 //DLL的端口号
}
```

---

