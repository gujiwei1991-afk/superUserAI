# 3、发送消息

> 来源: showdoc.com.cn/mrsanshui (cat_id=5561947)

## 发送文本消息

页面 ID: `10976065490942377` · 链接: https://www.showdoc.com.cn/mrsanshui/10976065490942377

**简要描述：**

- 发送文本消息

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 接收者的ID/群ID |
| msg | 是 | string | 文本消息 |

**发送示例：**

```json
{
    "type": 3000,
    "user_id": "788xxx",
    "msg": "你好鸭"
}
```

---

## 发送图片消息

页面 ID: `10976066402313019` · 链接: https://www.showdoc.com.cn/mrsanshui/10976066402313019

**简要描述：**

- 发送图片消息

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 接收者的ID/群ID |
| path | 是 | string | 图片绝对路径 |

**发送示例：**

```json
{
    "type": 3001,
    "user_id": "788xxx",
    "path": "C:\\Users\\Administrator\\Desktop\\1.png"
}
```

---

## 发送GIF表情

页面 ID: `10976066813506160` · 链接: https://www.showdoc.com.cn/mrsanshui/10976066813506160

**简要描述：**

- 发送GIF表情

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 接收者的ID/群ID |
| path | 是 | string | gif图片的绝对路径 |

**发送示例：**

```json
{
    "type": 3002,
    "user_id": "788xxx",
    "path": "C:\\Users\\Administrator\\Desktop\\1.gif"
}
```

---

## 发送文件消息

页面 ID: `10976067591400092` · 链接: https://www.showdoc.com.cn/mrsanshui/10976067591400092

**简要描述：**

- 发送文件消息

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 接收者的ID/群ID |
| path | 是 | string | 文件的绝对路径 |

**发送示例：**

```json
{
    "type": 3003,
    "user_id": "788xxx",
    "path": "C:\\Users\\Administrator\\Desktop\\1.text"
}
```

---

## 发送视频消息

页面 ID: `10976068464259666` · 链接: https://www.showdoc.com.cn/mrsanshui/10976068464259666

**简要描述：**

- 发送视频消息

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 接收者的ID/群ID |
| path | 是 | string | 视频的绝对路径 |

**发送示例：**

```json
{
    "type": 3004,
    "user_id": "788xxx",
    "path": "C:\\Users\\Administrator\\Desktop\\1.mp4"
}
```

---

## 发送名片

页面 ID: `10976068700501570` · 链接: https://www.showdoc.com.cn/mrsanshui/10976068700501570

**简要描述：**

- 发送名片

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 接收者的ID/群ID |
| friend_user_id | 是 | string | 好友的ID |

**发送示例：**

```json
{
    "type": 3005,
    "user_id": "788xxx",
    "friend_user_id": "788xxx"
}
```

---

## 发送小程序

页面 ID: `10976068884595908` · 链接: https://www.showdoc.com.cn/mrsanshui/10976068884595908

**简要描述：**

- 发送小程序

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 接收者的ID/群ID |
| title | 是 | string | 标题 |
| desc | 是 | string | 描述信息 |
| avatar_url | 是 | string | 头像地址 |
| cover_path | 是 | string | 封面图的绝对路径 |
| app_id | 是 | string | 小程序的appId(消息推送中获取) |
| wechat_id | 是 | string | 小程序的wechatId(消息推送中获取) |
| page_path | 是 | string | 小程序页面路径 |

**发送示例：**

```json
{
    "type": 3006,
    "user_id": "788xxx",
    "title": "标题",
    "desc": "描述信息",
    "avatar_url": "http://mmbiz.qpic.cn/mmbiz_png/xxx",
    "cover_path": "C:\\Users\\Administrator\\Desktop\\1.png",
    "app_id": "wx45xxx",
    "wechat_id": "gh_xxx@app",
    "page_path": "pages/train/index/index.html"
}
```

---

## 发送视频号

页面 ID: `10976069765828156` · 链接: https://www.showdoc.com.cn/mrsanshui/10976069765828156

**简要描述：**

- 发送视频号

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 接收者的ID/群ID |
| cover_url | 是 | string | 封面地址 |
| thumb_url | 是 | string | 略缩图地址 |
| avatar_url | 是 | string | 头像地址 |
| nick_name | 是 | string | 昵称 |
| desc | 是 | string | 描述信息 |
| video_url | 是 | string | 视频地址（推送消息中获取） |
| extras | 是 | string | 视频标识（推送消息中获取） |

**发送示例：**

```json
{
    "type": 3007,
    "user_id": "788xxx",
    "cover_url": "http://wxapp.tc.qq.com/251/20304/xxx",
    "thumb_url": "http://wxapp.tc.qq.com/251/20304/xxx",
    "avatar_url": "https://wx.qlogo.cn/finderhead/ver_1/xxx",
    "nick_name": "昵称",
    "desc": "描述信息",
    "video_url": "https://channels.weixin.qq.com/web/pages/xx",
    "extras": "CAEQxxxxxxxxxxx"
}
```

---

## 发送卡片链接

页面 ID: `10976070171704206` · 链接: https://www.showdoc.com.cn/mrsanshui/10976070171704206

**简要描述：**

- 发送卡片链接

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | int | 接收者的ID/群ID |
| title | 是 | int | 卡片标题 |
| desc | 是 | int | 卡片描述 |
| target_url | 是 | int | 目标地址 |
| cover_url | 是 | int | 封面地址 |

**发送示例：**

```json
{
    "type": 3008,
    "user_id": "788xxx",
    "title": "我是标题",
    "desc": "我是描述信息",
    "target_url": "https://www.baidu.com",
    "cover_url": "http://img.alicdn.com/imgextra/i2/1031524252/xxx.jpg"
}
```

---

## 群聊发送消息并且@指定群成员

页面 ID: `10976070648991107` · 链接: https://www.showdoc.com.cn/mrsanshui/10976070648991107

**简要描述：**

- 群聊发送消息并且@指定群成员

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| chat_room_id | 是 | string | 群ID |
| at_list | 是 | array | @人的ID列表 |
| msg | 是 | string | 文本消息 |

**发送示例：**

```json
{
    "type": 3009,
    "chat_room_id": "R:109xxx",
    "at_list": [
		"788xxx",
		"789xxx"
	],
    "msg": "你们快看"
}
```

---

## 发送位置消息

页面 ID: `10976070878267658` · 链接: https://www.showdoc.com.cn/mrsanshui/10976070878267658

**简要描述：**

- 发送位置消息

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 接收者的ID/群ID |
| lon | 是 | float | 经度 |
| lat | 是 | float | 纬度 |
| address | 是 | string | 地址 |
| detail_address | 是 | string | 详细地址 |

**发送示例：**

```json
{
    "type": 3010,
    "user_id": "788xxx",
    "lon": 90.0,
    "lat": 0.0,
    "address": "北极",
    "detail_address": "一块冰面上"
}
```

---

## 发送语音消息

页面 ID: `10976071446324232` · 链接: https://www.showdoc.com.cn/mrsanshui/10976071446324232

**简要描述：**

- 发送语音消息，搭配CDN上传接口使用（上传silk文件）

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 接收者的ID/群ID |
| cdn_key | 是 | string | CDN上传接口的返回值 |
| aes_key | 是 | string | CDN上传接口的返回值 |
| md5 | 是 | string | CDN上传接口的返回值 |
| size | 是 | int | CDN上传接口的返回值 |
| voice_time | 是 | int | 语音时长，单位：秒 |

**发送示例：**

```json
{
    "type": 3011,
    "user_id": "788xxx",
    "cdn_key": "30818902010000000000000000000000000000",
    "aes_key": "34653962300000000000000",
    "md5": "d6d3db33xxxxx",
    "size": 32136,
    "voice_time": 15
}
```

---

## 发送图片消息【CDN方式】

页面 ID: `11559060626603746` · 链接: https://www.showdoc.com.cn/mrsanshui/11559060626603746

**简要描述：**

- CDN发送图片，搭配CDN上传接口使用（该接口比常规的发送接口更高效、稳定；且资源可复用，降低内存开销）

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 接收者的ID/群ID |
| cdn_key | 是 | string | CDN上传接口的返回值 |
| aes_key | 是 | string | CDN上传接口的返回值 |
| md5 | 是 | string | CDN上传接口的返回值 |
| size | 是 | int | CDN上传接口的返回值 |

**发送示例：**

```json
{
    "type": 3013,
    "user_id": "788xxx",
    "cdn_key": "30818902010000000000000000000000000000",
    "aes_key": "34653962300000000000000",
    "md5": "d6d3db33xxxxx",
    "size": 32136
}
```

---

## 发送文件消息【CDN方式】

页面 ID: `11559060626603748` · 链接: https://www.showdoc.com.cn/mrsanshui/11559060626603748

**简要描述：**

- CDN发送文件，搭配CDN上传接口使用（该接口比常规的发送接口更高效、稳定；且资源可复用，降低内存开销）

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 接收者的ID/群ID |
| cdn_key | 是 | string | CDN上传接口的返回值 |
| aes_key | 是 | string | CDN上传接口的返回值 |
| md5 | 是 | string | CDN上传接口的返回值 |
| size | 是 | int | CDN上传接口的返回值 |
| file_name | 是 | string | CDN上传接口的返回值 |

**发送示例：**

```json
{
    "type": 3015,
    "user_id": "788xxx",
    "cdn_key": "30818902010000000000000000000000000000",
    "aes_key": "34653962300000000000000",
    "md5": "d6d3db33xxxxx",
    "size": 32136,
	"file_name": "1.exe"
}
```

---

## 发送视频消息【CDN方式】

页面 ID: `11559060626603747` · 链接: https://www.showdoc.com.cn/mrsanshui/11559060626603747

**简要描述：**

- CDN发送视频，搭配CDN上传接口使用（该接口比常规的发送接口更高效、稳定；且资源可复用，降低内存开销）

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 接收者的ID/群ID |
| cdn_key | 是 | string | CDN上传接口的返回值 |
| aes_key | 是 | string | CDN上传接口的返回值 |
| md5 | 是 | string | CDN上传接口的返回值 |
| size | 是 | int | CDN上传接口的返回值 |
| video_time | 是 | int | 视频时长，单位：秒 |

**发送示例：**

```json
{
    "type": 3014,
    "user_id": "788xxx",
    "cdn_key": "30818902010000000000000000000000000000",
    "aes_key": "34653962300000000000000",
    "md5": "d6d3db33xxxxx",
    "size": 32136,
	"video_time": 13
}
```

---

