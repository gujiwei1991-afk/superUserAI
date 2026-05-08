# 8、开放平台

> 来源: showdoc.com.cn/mrsanshui (cat_id=5561952)

## 企业用户ID转开放平台ID

页面 ID: `10976095097594674` · 链接: https://www.showdoc.com.cn/mrsanshui/10976095097594674

**简要描述：**

- 企业用户ID转开放平台ID

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 用户ID |

**发送示例：**

```json
{
    "type": 8000,
    "user_id": "788xxx"
}
```

**返回示例：**

```json
{
    "data": {
        "open_id": "wmfxxxxxxxxxxxxxxxx"
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## 企业群ID转开放平台ID

页面 ID: `10976096017763415` · 链接: https://www.showdoc.com.cn/mrsanshui/10976096017763415

**简要描述：**

- 企业群ID转开放平台ID

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| chat_room_id | 是 | string | 群ID |

**发送示例：**

```json
{
    "type": 8001,
    "chat_room_id": "R:108xxx"
}
```

**返回示例：**

```json
{
    "data": {
        "open_id": "wrfxxxxxxxxxxxxxxxxxxx"
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## 开放平台ID转企业用户ID

页面 ID: `10976096758788568` · 链接: https://www.showdoc.com.cn/mrsanshui/10976096758788568

**简要描述：**

- 开放平台ID转企业用户ID

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| open_id | 是 | string | 开放平台ID |

**发送示例：**

```json
{
    "type": 8002,
    "open_id": "wmfxxxxxxxxxxxxxxxxx"
}
```

**返回示例：**

```json
{
    "data": {
        "user_id": "788xxx"
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## 开放平台ID转企业群ID

页面 ID: `10976097034710010` · 链接: https://www.showdoc.com.cn/mrsanshui/10976097034710010

**简要描述：**

- 开放平台ID转企业群ID

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| open_id | 是 | string | 开放平台ID |

**发送示例：**

```json
{
    "type": 8003,
    "open_id": "wrfxxxxxxxxxxxxxxxxxx"
}
```

**返回示例：**

```json
{
    "data": {
        "char_room_id": "R:108xxx"
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

