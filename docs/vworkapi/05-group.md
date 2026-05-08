# 5、群操作

> 来源: showdoc.com.cn/mrsanshui (cat_id=5561949)

## 创建群聊【外部】

页面 ID: `10976078116793704` · 链接: https://www.showdoc.com.cn/mrsanshui/10976078116793704

**简要描述：**

- 创建群聊【外部】

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| name | 是 | str | 群名称 |
| user_id_list | 是 | array | 邀请进群的用户ID列表 |


**发送示例：**

```json
{
    "type": 5000,
    "name": "我是群聊名称",
    "user_id_list": [
        "788xxx1",
        "788xxx2"
    ]
}
```

**返回示例：**

```json
{
    "data": {
        "chat_room_id": "R:108xxx"
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## 创建群聊【内部】

页面 ID: `10976078643605140` · 链接: https://www.showdoc.com.cn/mrsanshui/10976078643605140

**简要描述：**

- 创建群聊【内部】

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| name | 是 | string | 群名称 |
| user_id_list | 是 | array | 邀请进群的用户ID列表 |

**发送示例：**

```json
{
    "type": 5001,
    "name": "我是群聊名称",
    "user_id_list": [
        "168xxx1",
        "168xxx2"
    ]
}
```

**返回示例：**

```json
{
    "data": {
        "chat_room_id": "R:333xxx"
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## 修改群名称

页面 ID: `10976079438336226` · 链接: https://www.showdoc.com.cn/mrsanshui/10976079438336226

**简要描述：**

- 修改群名称

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| chat_room_id | 是 | string | 群ID |
| name | 是 | string | 群名称 |

**发送示例：**

```json
{
    "type": 5002,
    "chat_room_id": "R:108xxx",
    "name": "我是修改后的群名称"
}
```

---

## 发送群公告

页面 ID: `10976079731639711` · 链接: https://www.showdoc.com.cn/mrsanshui/10976079731639711

**简要描述：**

- 发送群公告

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| chat_room_id | 是 | string | 群ID |
| content | 是 | string | 公告内容 |

**发送示例：**

```json
{
    "type": 5003,
    "chat_room_id": "R:108xxx",
    "content": "我是群公告内容"
}
```

---

## 邀请好友进群（40人以下）

页面 ID: `10976079863810129` · 链接: https://www.showdoc.com.cn/mrsanshui/10976079863810129

**简要描述：**

- 邀请好友进群（40人以下）

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| chat_room_id | 是 | string | 群ID |
| user_id_list | 是 | array | 用户ID列表 |

**发送示例：**

```json
{
    "type": 5004,
    "chat_room_id": "R:109xxx",
    "user_id_list": [
        "788xxx1",
        "788xxx2"
    ]
}
```

---

## 邀请好友进群（40人以上）

页面 ID: `10976080171700547` · 链接: https://www.showdoc.com.cn/mrsanshui/10976080171700547

**简要描述：**

- 邀请好友进群（40人以上）

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| chat_room_id | 是 | string | 群ID |
| user_id_list | 是 | array | 用户ID列表 |

**发送示例：**

```json
{
    "type": 5005,
    "chat_room_id": "R:109xxx",
    "user_id_list": [
        "788xxx1",
        "788xxx2"
    ]
}
```

---

## 删除群成员

页面 ID: `10976080831822522` · 链接: https://www.showdoc.com.cn/mrsanshui/10976080831822522

**简要描述：**

- 删除群成员

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| chat_room_id | 是 | string | 群ID |
| user_id_list | 是 | array | 用户ID列表 |

**发送示例：**

```json
{
    "type": 5006,
    "chat_room_id": "R:109xxx",
    "user_id_list": [
        "788xxx1",
        "788xxx2"
    ]
}
```

---

## 获取群二维码

页面 ID: `10976081177516984` · 链接: https://www.showdoc.com.cn/mrsanshui/10976081177516984

**简要描述：**

- 获取群二维码，群成员达到一定数量后，不可通过二维码进群，只能通过邀请链接进群，此时调用该接口会导致失败

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| chat_room_id | 是 | string | 群ID |
| path | 是 | string | 保存二维码的绝对路径 |

**发送示例：**

```json
{
    "type": 5007,
    "chat_room_id": "R:129xxx",
    "path": "C:\\Users\\Administrator\\Desktop\\room_qrcode.png"
}
```

---

## 获取群信息

页面 ID: `10976081930130586` · 链接: https://www.showdoc.com.cn/mrsanshui/10976081930130586

**简要描述：**

- 获取群信息

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
    "type": 5008,
    "chat_room_id": "R:109xxx"
}
```

**返回示例：**

```json
{
    "data": {
        "chat_room_id": "R:109xxx", //群ID
        "chat_room_type": 1, //群类型 0:内部群 1:外部群
        "create_time": 1619799671, //创建时间
        "create_user_id": "168xxx", //创建者ID
        "nick_name": "测试外部群", //群名
        "total": 8 //群成员数量
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## 获取欢迎语列表

页面 ID: `10976082619957001` · 链接: https://www.showdoc.com.cn/mrsanshui/10976082619957001

**简要描述：**

- 获取欢迎语列表

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |

**发送示例：**

```json
{
    "type": 5009
}
```

**返回示例：**

```json
{
    "data": {
		"list": [
			{
				"card_link": {
					"title": "我是标题", //标题
					"desc": "我是描述", //描述
                    "cover_url": "https://www.baidu/xxxxxxx.png", //封面地址
                    "target_url": "https://www.baidu.com/" //目标地址
                },
				"create_time": "16000", //创建时间
				"create_user_id": "788xxx", //创建人ID
				"welcome_id": 1, //欢迎语ID
				"content": "我是内容" //欢迎语内容
			},
			...
		]
	},
    "errmsg": "OK",
    "errno": 0
}
```

---

## 添加欢迎语

页面 ID: `10976083305151542` · 链接: https://www.showdoc.com.cn/mrsanshui/10976083305151542

**简要描述：**

- 添加欢迎语

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| content | 是 | array | 欢迎语 |
| card_link | 否 | object | 卡片链接 |

**发送示例：**

```json
{
    "type": 5010,
    "content": "欢迎加入\r\n请点击下方链接，阅读群规则",
    "card_link": {
        "title": "我是标题",
        "desc": "我是描述",
        "target_url": "http://www.baidu.com",
        "cover_url": "http://img.alicdn.com/xxx.jpg"
    }
}
```

**返回示例：**

```json
{
    "data": {
        "welcome_id": 6 //欢迎语ID
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## 设置欢迎语

页面 ID: `10976083589855817` · 链接: https://www.showdoc.com.cn/mrsanshui/10976083589855817

**简要描述：**

- 设置欢迎语

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| chat_room_id | 是 | string | 群ID |
| welcome_id | 是 | int | 欢迎语列表中的ID |

**发送示例：**

```json
{
    "type": 5011,
    "chat_room_id": "R:108xxx",
    "welcome_id": 8
}
```

---

## 移除欢迎语

页面 ID: `10976084172245382` · 链接: https://www.showdoc.com.cn/mrsanshui/10976084172245382

**简要描述：**

- 移除欢迎语

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
    "type": 5012,
    "chat_room_id": "R:108xxx"
}
```

---

## 添加管理员

页面 ID: `10976085107661795` · 链接: https://www.showdoc.com.cn/mrsanshui/10976085107661795

**简要描述：**

- 添加管理员

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| chat_room_id | 是 | string | 群ID |
| user_id_list | 是 | array | 用户ID列表 |

**发送示例：**

```json
{
    "type": 5013,
    "chat_room_id": "R:108xxx",
    "user_id_list": [
        "788xxx1",
        "788xxx2"
    ]
}
```

---

## 删除管理员

页面 ID: `10976085585572029` · 链接: https://www.showdoc.com.cn/mrsanshui/10976085585572029

**简要描述：**

- 删除管理员

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| chat_room_id | 是 | string | 群ID |
| user_id_list | 是 | array | 用户ID列表 |

**发送示例：**

```json
{
    "type": 5014,
    "chat_room_id": "R:108xxx",
    "user_id_list": [
        "788xxx1",
        "788xxx2"
    ]
}
```

---

## 转让群主

页面 ID: `10976086558344271` · 链接: https://www.showdoc.com.cn/mrsanshui/10976086558344271

**简要描述：**

- 转让群主

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| chat_room_id | 是 | string | 群ID |
| user_id | 是 | string | 用户ID |

**发送示例：**

```json
{
    "type": 5015,
    "chat_room_id": "R:109xxx",
    "user_id": "168xxx"
}
```

---

## 退出群聊

页面 ID: `10976086708442410` · 链接: https://www.showdoc.com.cn/mrsanshui/10976086708442410

**简要描述：**

- 退出群聊，内部群可以直接退，外部群如果你是群主，必须先转让群主后才能退

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
    "type": 5016,
    "chat_room_id": "R:109xxx"
}
```

---

## 解散群聊

页面 ID: `10976087610392346` · 链接: https://www.showdoc.com.cn/mrsanshui/10976087610392346

**简要描述：**

- 解散群聊

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
    "type": 5017,
    "chat_room_id": "R:108xxx"
}
```

---

## 允许/禁止修改群名

页面 ID: `10976087769126251` · 链接: https://www.showdoc.com.cn/mrsanshui/10976087769126251

**简要描述：**

- 允许/禁止修改群名

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| chat_room_id | 是 | string | 群ID |
| state | 是 | int | 1:允许 0:禁止 |

**发送示例：**

```json
{
    "type": 5018,
    "chat_room_id": "R:108xxx",
    "state": 0
}
```

---

## 开启/关闭邀请确认

页面 ID: `10976088108547966` · 链接: https://www.showdoc.com.cn/mrsanshui/10976088108547966

**简要描述：**

- 开启/关闭邀请确认

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| chat_room_id | 是 | string | 群ID |
| state | 是 | int | 1:开启 0:关闭 |

**发送示例：**

```json
{
    "type": 5019,
    "chat_room_id": "R:108xxx",
    "state": 1
}
```

---

