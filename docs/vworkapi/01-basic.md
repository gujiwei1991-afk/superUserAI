# 1、基础功能

> 来源: showdoc.com.cn/mrsanshui (cat_id=5561945)

## 获取登录状态

页面 ID: `10976058505633655` · 链接: https://www.showdoc.com.cn/mrsanshui/10976058505633655

**简要描述：**

- 获取登录状态

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
    "type": 1000
}
```

**返回示例：**

```json
{
    "data": {
        "status": 1 //0未登录 1已登录
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## 刷新并获取登录二维码

页面 ID: `10976059142001962` · 链接: https://www.showdoc.com.cn/mrsanshui/10976059142001962

**简要描述：**

- 刷新并获取登录二维码

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| path | 是 | string | 保存二维码的绝对路径 |

**发送示例：**

```json
{
    "type": 1001,
    "path": "C:\\Users\\Administrator\\Desktop\\qrcode.png"
}
```

---

## 获取个人信息

页面 ID: `10976059939446664` · 链接: https://www.showdoc.com.cn/mrsanshui/10976059939446664

**简要描述：**

- 获取个人信息

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
    "type": 1002
}
```

**返回示例：**

```json
{
    "data": {
        "alias": "sanshui", //别名
        "avatar_url": "https://thirdwx.qlogo.cn/xxx/0", //头像地址
        "corp_id": "197xxx", //公司ID
        "corp_name": "xxx有限公司", //公司全称
        "corp_short_name": "xxx", //公司简称
        "dept_id": "168xxx", //部门ID
        "dept_name": "xxx", //部门名称
        "email": "xxx@163.com", //邮箱
        "job_name": "CEO", //职位
        "mobile": "13800000000", //手机号
        "nick_name": "三水君", //昵称
        "position": "CEO", //职位
        "real_name": "xxx", //真实姓名
        "sex": "1", //性别 0:未设置 1:男 2:女
        "user_id": "168xxx" //用户ID
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## 退出登录

页面 ID: `10976060816114127` · 链接: https://www.showdoc.com.cn/mrsanshui/10976060816114127

**简要描述：**

- 退出登录

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
    "type": 1003
}
```

---

## 获取个人二维码

页面 ID: `10976061670134071` · 链接: https://www.showdoc.com.cn/mrsanshui/10976061670134071

**简要描述：**

- 获取个人二维码

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
    "type": 1004
}
```

**返回示例：**

```json
{
    "data": {
        "qrcode_url": "https://wework.qpic.cn/xxx/xxx/0" //二维码地址
    },
    "errmsg": "OK",
    "errno": 0
}
```

---

## 输入登录验证码

页面 ID: `11115907156268078` · 链接: https://www.showdoc.com.cn/mrsanshui/11115907156268078

**简要描述：**

- 输入登录验证码

**请求URL：**

- `http://127.0.0.1:8989/api`

**请求方式：**

- POST

**JSON参数：**

| 参数名 | 是否必选 | 类型 | 说明 |
|:--- |:--- |:--- |:---  |
| type | 是 | int | 消息类型 |
| code | 是 | string | 手机上收到的验证码 |

**发送示例：**

```json
{
    "type": 1005,
	"code": "520520"
}
```

---

