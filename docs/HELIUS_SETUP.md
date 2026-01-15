# Helius API 配置指南

## 📋 概述

Helius是专门针对Solana区块链的数据服务提供商，提供高性能的RPC节点和增强型API。本指南说明如何在信号机器人中配置和使用Helius API。

## 🔑 获取API密钥

### 步骤1：注册账户

1. 访问 [Helius官网](https://www.helius.dev/)
2. 点击"Sign Up"注册账户
3. 完成邮箱验证

### 步骤2：创建API密钥

1. 登录后进入Dashboard
2. 点击"Create API Key"
3. 选择免费计划（Free Tier）
4. 复制生成的API密钥

### 步骤3：配置API密钥

在项目根目录的`.env`文件中添加：

```env
HELIUS_API_KEY=your_helius_api_key_here
```

## 📊 免费计划限制

根据[Helius官方文档](https://www.helius.dev/docs/zh/billing/plans)，免费计划限制：

**免费层（Free Tier）**：
- ✅ **定价**：$0/月
- ✅ **每月积分**：1M（100万积分）
- ✅ **RPC速率限制**：10 req/s
- ⚠️ **DAS API**：2 req/s
- ⚠️ **增强API**：2 req/s
- ✅ **WebSockets**：包含
- ❌ **增强WebSockets**：不支持
- ❌ **LaserStream (gRPC)**：不支持
- ✅ **支持级别**：社区支持

**对比DexScreener**：
- DexScreener：60次/分钟 = 1次/秒
- Helius RPC：10次/秒 = **600次/分钟**（优势明显）
- Helius DAS/增强API：2次/秒 = **120次/分钟**（仍优于DexScreener）

**重要说明**：
- 当前实现使用`getAsset`方法（RPC端点），受RPC限制（10 req/s）
- 如果未来使用DAS API或增强API，需要遵守2 req/s的限制
- 系统已实现自动限流，无需手动控制

## 🎯 使用场景

### 自动检测

系统会自动检测代币地址类型：

- **Solana地址**（32-44字符，Base58编码）
  - 例如：`So11111111111111111111111111111111111111112`
  - 自动使用Helius适配器

- **以太坊地址**（42字符，0x开头）
  - 例如：`0x1234567890123456789012345678901234567890`
  - 使用DexScreener适配器

### 手动指定

如果需要手动指定数据源，可以在代码中修改`_select_adapter`方法。

## 🔧 配置选项

### 环境变量

| 变量名 | 说明 | 必需 | 默认值 |
|--------|------|------|--------|
| `HELIUS_API_KEY` | Helius API密钥 | ✅ 是 | - |
| `HELIUS_PROXY_URL` | Helius API代理（可选） | ❌ 否 | - |

### 代理配置

如果需要通过代理访问Helius API，可以设置：

```env
HELIUS_PROXY_URL=http://127.0.0.1:7890
```

如果没有设置`HELIUS_PROXY_URL`，系统会使用`TG_PROXY_URL`作为回退。

## 📝 使用示例

### 示例1：监测Solana代币

在Telegram群组中发送Solana代币地址：

```
So11111111111111111111111111111111111111112
```

系统会自动：
1. 检测到这是Solana地址
2. 使用Helius适配器获取数据
3. 执行策略分析
4. 发送信号通知

### 示例2：监测以太坊代币

在Telegram群组中发送以太坊代币地址：

```
0x1234567890123456789012345678901234567890
```

系统会自动：
1. 检测到这是以太坊地址
2. 使用DexScreener适配器获取数据
3. 执行策略分析
4. 发送信号通知

## ⚠️ 注意事项

### 1. API密钥安全

- ✅ 不要将API密钥提交到Git仓库
- ✅ 使用`.env`文件存储密钥（已添加到`.gitignore`）
- ✅ 定期轮换API密钥

### 2. 速率限制

- Helius免费层：每秒10个请求
- 系统已实现自动限流，无需手动控制
- 如果超过限制，系统会自动等待

### 3. 数据可用性

- Helius专门针对Solana链，数据准确可靠
- 对于非Solana代币，系统会自动回退到DexScreener
- 如果Helius API不可用，系统会记录错误日志

## 🐛 故障排除

### 问题1：无法获取数据

**症状**：日志显示"Helius API密钥未配置"

**解决方案**：
1. 检查`.env`文件中是否设置了`HELIUS_API_KEY`
2. 确认API密钥格式正确（无多余空格）
3. 重启机器人

### 问题2：速率限制错误

**症状**：日志显示"API限流"警告

**解决方案**：
- 这是正常现象，系统会自动等待
- 如果频繁出现，考虑升级到付费计划

### 问题3：价格数据为None

**症状**：K线数据中价格字段为0或None

**解决方案**：
- 当前实现中，价格查询功能待完善
- 需要集成Jupiter API或其他价格聚合器
- 这是已知限制，不影响基础功能

## 📚 相关文档

- [Helius官方文档](https://www.helius.dev/docs)
- [可行性分析](./HELIUS_API_FEASIBILITY.md)
- [架构设计](../docs/ARCHITECTURE.md)
