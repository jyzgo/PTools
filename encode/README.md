## 目标

在当前目录提供一个 Python 脚本 `file_crypto.py`，可以通过 **key**（或密码派生 key）对任意文本/文件进行**加密与解密**。

## 安装

```bash
pip install -r requirements.txt
```

## 使用方法

### 方式 A：使用随机 key（推荐）

- **生成 key**（打印到屏幕）：

```bash
python file_crypto.py gen-key
```

- **生成 key**（保存到文件，比如 `my.key`）：

```bash
python file_crypto.py gen-key --out my.key
```

- **加密**（key 既可以直接传字符串，也可以传 key 文件路径）：

```bash
python file_crypto.py encrypt --in plain.txt --key my.key
```

默认输出：`plain.txt.enc`

- **解密**：

```bash
python file_crypto.py decrypt --in plain.txt.enc --key my.key
```

默认输出：`plain.txt.dec`

### 方式 B：使用密码（自动 PBKDF2 派生 key）

- **加密**（会自动生成随机 salt 并写入密文文件头）：

```bash
python file_crypto.py encrypt --in plain.txt --password "your-password"
```

- **解密**：

```bash
python file_crypto.py decrypt --in plain.txt.enc --password "your-password"
```

### 关于“短 key / 口令”（例如：`jyzgo?8511`）

从现在开始，`--key` 既支持 **Fernet key**，也支持把“短 key/口令”当作 passphrase（自动 PBKDF2 派生）使用。注意 PowerShell 下建议加引号：

```bash
python file_crypto.py encrypt --in plain.txt --key "jyzgo?8511"
python file_crypto.py decrypt --in plain.txt.enc --key "jyzgo?8511"
```

### 对比两个文件内容是否一致

```bash
python file_crypto.py compare a.txt b.txt
```

- 输出 `SAME` 表示一致（退出码 0）
- 输出 `DIFF` 表示不一致（退出码 3）

## 输出文件格式说明（ENVELOPE）

加密输出是一个简单的文本 envelope（便于拷贝/传输/检查），包含：

- `kdf`: `none` 或 `pbkdf2-sha256`
- `salt`: 仅在使用 `--password` 时存在
- `token`: 实际密文（Fernet token）

## 注意事项

- 请妥善保管 key / password；丢失后无法恢复明文。
- 如果解密报错通常是 **key/password 不正确** 或 **密文文件被修改**。


