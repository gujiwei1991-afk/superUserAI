# 6、标签操作

> 来源: showdoc.com.cn/mrsanshui (cat_id=5561950)

## 获取标签组列表

页面 ID: `10976088270057602` · 链接: https://www.showdoc.com.cn/mrsanshui/10976088270057602

**简要描述：**

- 获取标签组列表

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
    "type": 6000
}
```

**返回示例：**

```json
{
    "data": {
        "list": [
            {
                "create_time": "1708796042", //创建时间
                "group_id": "14073749414867782", //分组ID
                "group_name": "客户等级", //分组名
                "group_type": "1", //分组类型 1:企业标签 2:个人标签
                "label_list": [ //标签列表
                    {
                        "create_time": "1708796042", //创建时间
                        "label_id": "14073749414867783", //标签ID
                        "label_name": "一般" //标签名
                    },
                    ...
                ]
            },
            {
                "create_time": "1708796043", //创建时间
                "group_id": "14073753095818178", //分组ID
                "group_name": "个人标签", //分组名
                "group_type": "2", //分组类型 1:企业标签 2:个人标签
                "label_list": [ //标签列表
                    {
                        "create_time": "1709469367", //创建时间
                        "label_id": "14073749711835212", //标签ID
                        "label_name": "男的" //标签名
                    },
					...
                ]
            },
			...
        ]
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## 添加标签

页面 ID: `10976088618545670` · 链接: https://www.showdoc.com.cn/mrsanshui/10976088618545670

**简要描述：**

- 添加标签

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| group_id | 是 | string | 标签组ID |
| label_name | 是 | string | 标签名 |

**发送示例：**

```json
{
    "type": 6001,
    "group_id": "140000000000000",
    "label_name": "新的标签名"
}
```

---

## 修改标签

页面 ID: `10976089343150977` · 链接: https://www.showdoc.com.cn/mrsanshui/10976089343150977

**简要描述：**

- 修改标签

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| label_id | 是 | string | 标签ID |
| group_id | 是 | string | 标签组ID |
| label_name | 是 | string | 标签名 |

**发送示例：**

```json
{
    "type": 6002,
    "group_id": "1400000000000000",
	"label_id": "1400000000000001",
    "label_name": "新的标签名2"
}
```

---

## 删除标签

页面 ID: `10976090013776623` · 链接: https://www.showdoc.com.cn/mrsanshui/10976090013776623

**简要描述：**

- 删除标签

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| group_id | 是 | string | 标签组ID |
| label_id | 是 | string | 标签ID |

**发送示例：**

```json
{
    "type": 6003,
    "group_id": "1400000000000000",
	"label_id": "1400000000000001"
}
```

---

## 一个好友打多个标签

页面 ID: `10976090318233135` · 链接: https://www.showdoc.com.cn/mrsanshui/10976090318233135

**简要描述：**

- 一个好友打多个标签

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| user_id | 是 | string | 用户ID |
| label_id_list | 是 | array | 标签ID列表 |

**发送示例：**

```json
{
    "type": 6004,
    "user_id": "788xxx",
    "label_id_list": [
        "14000000000000001",
        "14000000000000002"
    ]
}
```

---

## 一个标签打多个好友

页面 ID: `10976091128498263` · 链接: https://www.showdoc.com.cn/mrsanshui/10976091128498263

**简要描述：**

- 一个标签打多个好友

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| label_id | 是 | string | 标签ID |
| user_id_list | 是 | array | 用户ID列表 |

**发送示例：**

```json
{
    "type": 6005,
    "label_id": "14000000000000001",
    "user_id_list": [
        "788xxx1",
        "788xxx2"
    ]
}
```

---

## 获取标签下的联系人

页面 ID: `10976092049568541` · 链接: https://www.showdoc.com.cn/mrsanshui/10976092049568541

**简要描述：**

- 获取标签下的联系人

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| label_id | 是 | string | 标签ID |

**发送示例：**

```json
{
    "type": 6006,
    "label_id": "14000000000000001"
}
```

**返回示例：**

```json
{
    "data": {
        "list": [ //用户ID列表
            "788xxx1",
            "788xxx2"
        ]
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## 删除标签下的联系人

页面 ID: `10976092623642675` · 链接: https://www.showdoc.com.cn/mrsanshui/10976092623642675

**简要描述：**

- 删除标签下的联系人

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| label_id | 是 | string | 标签ID |
| user_id_list | 是 | array | 用户ID列表 |

**发送示例：**

```json
{
    "type": 6007,
    "label_id": "14000000000000001",
    "user_id_list": [
        "788xxx1",
        "788xxx2"
    ]
}
```

---

