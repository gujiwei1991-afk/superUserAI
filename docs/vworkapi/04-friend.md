# 4、好友操作

> 来源: showdoc.com.cn/mrsanshui (cat_id=5561948)

## 添加好友【群成员】

页面 ID: `10976072374994009` · 链接: https://www.showdoc.com.cn/mrsanshui/10976072374994009

**简要描述：**

- 添加好友【群成员】，调用成功后，对方个微收到新朋友请求

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
| msg | 是 | string | 添加时的打招呼消息 |

**发送示例：**

```json
{
    "type": 4000,
    "chat_room_id": "R:108xxx",
    "user_id": "788xxx",
    "msg": "你好啊"
}
```

---

## 添加好友【网络查询】

页面 ID: `10976073305646294` · 链接: https://www.showdoc.com.cn/mrsanshui/10976073305646294

**简要描述：**

- 添加好友【网络查询】，搭配《网络查询陌生人信息》接口使用，调用成功后，对方个微收到邀请加好友的服务通知

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| add_type | 是 | int | 添加类型 1:企微 2:个微 |
| corp_id | 否（add_type=1时必传） | string | 网络查询陌生人信息中获取 |
| user_id | 是 | string | 网络查询陌生人信息中获取 |
| openid_or_ticket | 是 | string | openid或者ticket<br>(网络查询陌生人信息中获取) |
| msg | 是 | string | 添加时的打招呼消息 |

**发送示例（添加企微）：**

```json
{
    "type": 4009,
    "add_type": 1,
    "corp_id": "197xxx",
    "user_id": "312xxx",
    "openid_or_ticket": "6A4EABDB0F26Axxxxxxxxxxxxx",
    "msg": "你好啊"
}
```

**发送示例（添加个微）：**

```json
{
    "type": 4009,
    "add_type": 2,
    "user_id": "788xxx",
    "openid_or_ticket": "orFxxxxxxxx",
    "msg": "你好啊"
}
```

---

## 删除好友

页面 ID: `10976073889995459` · 链接: https://www.showdoc.com.cn/mrsanshui/10976073889995459

**简要描述：**

- 删除好友

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
    "type": 4001,
    "user_id": "788xxx"
}
```

---

## 同意好友请求

页面 ID: `10976074524552997` · 链接: https://www.showdoc.com.cn/mrsanshui/10976074524552997

**简要描述：**

- 同意好友请求

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 消息推送中获取 |
| corp_id | 是 | string | 消息推送中获取 |

**发送示例：**

```json
{
    "type": 4002,
    "user_id": "788xxx",
	"corp_id": "197000000000"
}
```

---

## 设置好友备注

页面 ID: `10976075346513229` · 链接: https://www.showdoc.com.cn/mrsanshui/10976075346513229

**简要描述：**

- 设置好友备注

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 用户ID |
| remark | 是 | string | 备注信息 |

**发送示例：**

```json
{
    "type": 4003,
    "user_id": "788xxx",
    "remark": "备注"
}
```

---

## 设置好友描述

页面 ID: `10976076057443646` · 链接: https://www.showdoc.com.cn/mrsanshui/10976076057443646

**简要描述：**

- 设置好友描述

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 用户ID |
| desc | 是 | string | 描述信息 |

**发送示例：**

```json
{
    "type": 4004,
    "user_id": "788xxx",
    "desc": "描述"
}
```

---

## 设置好友公司

页面 ID: `10976076559510906` · 链接: https://www.showdoc.com.cn/mrsanshui/10976076559510906

**简要描述：**

- 设置好友公司，只支持外部联系人

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 用户ID |
| corp_name | 是 | string | 公司名称 |


**发送示例：**

```json
{
    "type": 4005,
    "user_id": "788xxx",
    "corp_name": "公司名称"
}
```

---

## 设置好友手机号

页面 ID: `10976076820772491` · 链接: https://www.showdoc.com.cn/mrsanshui/10976076820772491

**简要描述：**

- 设置好友手机号，只支持外部联系人

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 用户ID |
| mobile_list | 是 | array | 手机号列表 |

**发送示例：**

```json
{
    "type": 4006,
    "user_id": "788xxx",
    "mobile_list": [
        "138000000",
        "139000000"
    ]
}
```

---

## 本地查询好友信息

页面 ID: `10976077162440019` · 链接: https://www.showdoc.com.cn/mrsanshui/10976077162440019

**简要描述：**

- 本地查询好友信息

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
    "type": 4007,
    "user_id": "788xxx"
}
```

**返回示例：**

```json
{
    "data": {
        "add_time": "1619799671", //添加时间
        "avatar_url": "https://thirdwx.qlogo.cn/mmopen/vi_32/xxx/0", //头像地址
        "corp_id": "197xxx", //公司ID
        "corp_name": "xxx有限公司", //公司全称
		"corp_remark": "备注-XXX公司", //公司备注
        "corp_short_name": "xxx", //公司简称
        "dept_id": "168xxx", //部门ID
        "dept_name": "打杂部", //部门名称
        "desc": "我是描述信息", //描述
        "mobile": "13800000000", //手机号
        "nick_name": "三水君", //昵称
        "position": "CEO", //职位
        "real_name": "xxx", //真实姓名
        "remark": "我是备注", //备注
        "remark_phone_list": [ //备注电话列表
			"13800000000",
			"13900000000"
		],
        "sex": "1", //性别 0:未设置 1:男 2:女
        "user_id": "168xxx" //用户ID
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## 网络查询陌生人信息

页面 ID: `10976077956807461` · 链接: https://www.showdoc.com.cn/mrsanshui/10976077956807461

**简要描述：**

- 网络查询陌生人信息

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| key | 是 | string | 手机号/邮箱号 |

**发送示例：**

```json
{
    "type": 4008,
    "key": "13800000000"
}
```

**返回示例：**

```json
{
    "data": {
        "list": [
            {
                "avatar_url": "https://wework.qpic.cn/wwpic3az/xxx/0", //头像地址
                "corp_id": "197xxx", //公司ID
                "item_type": 1, //微信类型 1:企微 2:个微
                "nick_name": "**君", //昵称
                "openid_or_ticket": "149Fxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", //添加为好友时需要用到
                "sex": "1", //性别 0:未设置 1:男 2:女
                "user_id": "312xxx" //用户ID
            },
            {
                "avatar_url": "http://wx.qlogo.cn/mmhead/xxx/0", //头像地址
                "corp_id": "", //公司ID
                "item_type": 2, //微信类型 1:企微 2:个微
                "nick_name": "三水君", //昵称
                "openid_or_ticket": "orFxxxxxxxxxxxxxxxxx", //添加为好友时需要用到
                "sex": "1", //性别 0:未设置 1:男 2:女
                "user_id": "788xxx" //用户ID
            }
        ]
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

