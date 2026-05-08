# 2、好友/群/成员/公司/部门 列表

> 来源: showdoc.com.cn/mrsanshui (cat_id=5561946)

## 获取好友列表【外部】

页面 ID: `10976061999731028` · 链接: https://www.showdoc.com.cn/mrsanshui/10976061999731028

**简要描述：**

- 获取好友列表【外部】

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| page_num | 是 | int | 当前页数 |
| page_size | 是 | int | 每页显示数量 |

**发送示例：**

```json
{
    "type": 2000,
    "page_num": 1,
    "page_size": 10
}
```

**返回示例：**

```json
{
    "data": {
        "list": [
            {
                "add_time": "1619799671", //添加时间
                "avatar_url": "https://wework.qpic.cn/wwpic/xxx/0", //头像地址
                "corp_id": "197xxx", //公司ID
                "desc": "我是描述信息", //描述信息
                "mobile": "1380000000", //手机号码
                "nick_name": "三水君", //昵称
                "position": "CEO", //职位
                "remark": "我是备注", //备注
                "remark_phone_list": [ //备注电话列表
                    "1380000000"
                ],
                "sex": "1", //性别 0:未设置 1:男 2:女
                "unionid": "ozynxxx", //关联ID
                "user_id": "168xxx" //用户ID
            },
			...
        ],
        "page_num": 1, //当前页数
        "page_size": 10, //每页显示数量
        "total": 5, //总数量
        "total_page": 1 //总页数
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## 获取好友列表【内部】

页面 ID: `10976062241735751` · 链接: https://www.showdoc.com.cn/mrsanshui/10976062241735751

**简要描述：**

- 获取好友列表【内部】

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| page_num | 是 | int | 当前页数 |
| page_size | 是 | int | 每页显示数量 |

**发送示例：**

```json
{
    "type": 2001,
    "page_num": 1,
    "page_size": 10
}
```

**返回示例：**

```json
{
    "data": {
        "list": [
            {
                "avatar_url": "https://wework.qpic.cn/wwpic/xxx/0", //头像地址
                "corp_id": "197xxx", //公司ID
                "dept_list": [ //部门列表
                    {
                        "id": "168xxx", //部门ID
                        "name": "xxx打杂部" //部门名称
                    }
                ],
                "desc": "我是描述信息", //描述信息
                "mobile": "1380000000", //手机号
                "nick_name": "三水君", //昵称
                "position": "CEO", //职位
                "remark": "我是备注", //备注
                "sex": "2", //性别 0:未设置 1:男 2:女
                "unionid": "ozynxxx", //关联ID
                "user_id": "168xxx" //用户ID
            },
			...
        ],
        "page_num": 1, //当前页数
        "page_size": 10, //每页显示数量
        "total": 204, //总数量
        "total_page": 21 //总页数
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## 获取群列表

页面 ID: `10976062844344233` · 链接: https://www.showdoc.com.cn/mrsanshui/10976062844344233

**简要描述：**

- 获取群列表，根据“is_external”字段来区分内部群还是外部群

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| page_num | 是 | int | 当前页数 |
| page_size | 是 | int | 每页显示数量 |

**发送示例：**

```json
{
    "type": 2002,
    "page_num": 1,
    "page_size": 10
}
```

**返回示例：**

```json
{
    "data": {
        "list": [
            {
                "chat_room_id": "R:239xxx", //群ID
                "create_time": "1619799671", //创建时间
                "create_user_id": "168xxx", //创建人ID
                "is_admin": "0", //是否为管理员 0:否 1:是
                "is_external": "0", //是否为外部群 0:内部群 1:外部群
                "nick_name": "测试的内部群", //群名
                "notice_content": "我是群公告啊啊啊", //群公告内容
                "notice_time": "1619799671", //群公告发布时间
                "notice_user_id": "168xxx", //群公告发送者ID
                "total": "3" //群成员数量
            },
			...
        ],
        "page_num": 1, //当前页数
        "page_size": 10, //每页显示数量
        "total": 8, //总数量
        "total_page": 1 //总页数
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## 获取群成员列表

页面 ID: `10976063519843170` · 链接: https://www.showdoc.com.cn/mrsanshui/10976063519843170

**简要描述：**

- 获取群成员列表

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
    "type": 2003,
    "chat_room_id": "R:197xxx"
}
```

**返回示例：**

```json
{
    "data": {
        "chat_room_id": "R:197xxx", //群ID
        "list": [
            {
                "avatar_url": "https://wework.qpic.cn/wwpic/xxx/0", //头像地址
                "corp_id": "197xxx", //公司ID
                "desc": "我是描述信息", //描述
                "invite_user_id": "168xxx", //邀请人ID
                "is_admin": "1", //是否为管理员 0:否 1:是
                "join_time": "1619799671", //进群时间
                "mobile": "1380000000", //手机号
                "nick_name": "三水君", //昵称,
				"room_nick_name": "我是群昵称", //群昵称
                "position": "",  //职位
                "remark": "我是备注", //备注
                "sex": "2", //性别 0:未设置 1:男 2:女
                "unionid": "ozyxxx", //关联ID
                "user_id": "168xxx" //用户ID
            },
			...
        ]
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## 获取公司列表

页面 ID: `10976064385572661` · 链接: https://www.showdoc.com.cn/mrsanshui/10976064385572661

**简要描述：**

- 获取公司列表

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
    "type": 2004
}
```

**返回示例：**

```json
{
    "data": {
        "list": [
            {
                "admin_id": "168xxx", //管理员ID
                "admin_name": "三水君", //管理员名称
                "avatar_url": "https://p.qlogo.cn/bizmail/xxx/0", //头像地址
                "corp_id": "197xxx", //公司ID
                "corp_name": "xxx有限公司", //公司全称
                "corp_short_name": "xxx", //公司简称
                "create_time": "1619799671", //创建时间
                "desc": "我是描述信息" //描述
            },
			...
        ]
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## 获取部门列表

页面 ID: `10976064934929217` · 链接: https://www.showdoc.com.cn/mrsanshui/10976064934929217

**简要描述：**

- 获取部门列表

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
    "type": 2005
}
```

**返回示例：**

```json
{
    "data": {
        "list": [
            {
                "dept_name": "打杂部", //部门名称
                "id": "168xxx", //部门ID
                "parent_id": "16xxx" //所属公司ID
            },
            ...
        ]
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

