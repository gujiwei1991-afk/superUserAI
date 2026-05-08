# 9、CDN 上下载

> 来源: showdoc.com.cn/mrsanshui (cat_id=5561953)

## CDN上传图片

页面 ID: `11559060626603744` · 链接: https://www.showdoc.com.cn/mrsanshui/11559060626603744

**简要描述：**

- CDN上传图片

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| path | 是 | string | 图片的绝对路径 |

**发送示例：**

```json
{
    "type": 9005,
    "path": "C:\\Users\\Administrator\\Desktop\\1.jpg"
}
```

**返回示例：**

```json
{
    "data": {
		"cdn_key": "3069020102000000000000000000000000",
        "aes_key": "64320000000000000000",
        "md5": "c8caaxxxxxxxxxxxxxxxxxxxxx",
        "size": 62725
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## CDN上传视频

页面 ID: `11559060626603745` · 链接: https://www.showdoc.com.cn/mrsanshui/11559060626603745

**简要描述：**

- CDN上传视频

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| path | 是 | string | 视频的绝对路径 |
| cover_path | 是 | string | 视频封面图的绝对路径 |

**发送示例：**

```json
{
    "type": 9006,
    "path": "C:\\Users\\Administrator\\Desktop\\1.mp4",
	"cover_path": "C:\\Users\\Administrator\\Desktop\\1.jpg"
}
```

**返回示例：**

```json
{
    "data": {
		"cdn_key": "3069020102000000000000000000000000",
        "aes_key": "64320000000000000000",
        "md5": "c8caaxxxxxxxxxxxxxxxxxxxxx",
        "size": 62725
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## CDN上传文件

页面 ID: `10976097705994392` · 链接: https://www.showdoc.com.cn/mrsanshui/10976097705994392

**简要描述：**

- CDN上传文件

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| path | 是 | string | 文件的绝对路径 |

**发送示例：**

```json
{
    "type": 9000,
    "path": "C:\\Users\\Administrator\\Desktop\\1.silk"
}
```

**返回示例：**

```json
{
    "data": {
		"cdn_key": "3069020102000000000000000000000000",
        "aes_key": "64320000000000000000",
        "md5": "c8caaxxxxxxxxxxxxxxxxxxxxx",
        "size": 62725,
		"file_name": "1.silk"
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## CDN下载图片

页面 ID: `11558678992082297` · 链接: https://www.showdoc.com.cn/mrsanshui/11558678992082297

**简要描述：**

- CDN下载图片

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| cdn_key | 是 | string | cdn_key（推送消息中获取） |
| aes_key | 是 | string | aes_key（推送消息中获取） |
| size | 是 | int | 图片大小（推送消息中获取） |
| img_type | 是 | int | 图片类型（推送消息中获取） |
| save_path | 是 | string | 保存图片的绝对路径 |

**发送示例：**

```json
{
    "type": 9001,
    "cdn_key": "30520201000xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
	"aes_key": "ba8221xxxxxxxxxxxxxxxxxxxxxxxxxx",
	"size": 230192,
	"img_type": 2,
	"save_path": "C:\\Users\\Administrator\\Desktop\\1.png"
}
```

---

## CDN下载视频

页面 ID: `11558678993879202` · 链接: https://www.showdoc.com.cn/mrsanshui/11558678993879202

**简要描述：**

- CDN下载视频

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| cdn_key | 是 | string | cdn_key（推送消息中获取） |
| aes_key | 是 | string | aes_key（推送消息中获取） |
| size | 是 | int | 视频大小（推送消息中获取） |
| save_path | 是 | string | 保存图片的绝对路径 |

**发送示例：**

```json
{
    "type": 9002,
    "cdn_key": "30520201000xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
	"aes_key": "ba8221xxxxxxxxxxxxxxxxxxxxxxxxxx",
	"size": 230192,
	"save_path": "C:\\Users\\Administrator\\Desktop\\1.mp4"
}
```

---

## CDN下载文件

页面 ID: `11558678994568413` · 链接: https://www.showdoc.com.cn/mrsanshui/11558678994568413

**简要描述：**

- CDN下载文件（不支持下载大文件）

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| cdn_key | 是 | string | cdn_key（推送消息中获取） |
| aes_key | 是 | string | aes_key（推送消息中获取） |
| size | 是 | int | 文件大小（推送消息中获取） |
| save_path | 是 | string | 保存图片的绝对路径 |

**发送示例：**

```json
{
    "type": 9003,
    "cdn_key": "30520201000xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
	"aes_key": "ba8221xxxxxxxxxxxxxxxxxxxxxxxxxx",
	"size": 230192,
	"save_path": "C:\\Users\\Administrator\\Desktop\\1.exe"
}
```

---

## CDN下载个微图片/视频/文件

页面 ID: `11558678994946589` · 链接: https://www.showdoc.com.cn/mrsanshui/11558678994946589

**简要描述：**

- CDN下载个微图片/视频/文件

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| url | 是 | string | url（推送消息中获取） |
| auth_key | 是 | string | auth_key（推送消息中获取） |
| aes_key | 是 | string | aes_key（推送消息中获取） |
| size | 是 | int | 资源大小（推送消息中获取） |
| save_path | 是 | string | 保存图片的绝对路径 |

**发送示例：**

```json
{
    "type": 9004,
    "url": "https://imunion.xx.com/xxxxxx",
	"auth_key": "v1_1ab409d17xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
	"aes_key": "eed1bdxxxxxxxxxxxxxxxxxxxxxxxxxx",
	"size": 6002,
	"save_path": "C:\\Users\\Administrator\\Desktop\\1.jpg"
}
```

---

