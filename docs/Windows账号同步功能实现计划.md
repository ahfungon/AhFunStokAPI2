# Windows 版本账号同步功能实现计划

## 📅 文档信息
- **创建日期**: 2025-01-XX
- **文档版本**: 1.0
- **目标平台**: Windows (VB.NET)
- **参考实现**: iOS/Mac 应用账号同步功能

---

## 一、需求概述

### 1.1 功能目标
为 Windows 版本的摸鱼看盘应用（AhFunStock_Win）增加账号同步功能，实现与 iOS/Mac 应用的数据同步，让用户可以在不同设备间无缝切换，保持股票配置的一致性。

### 1.2 核心需求
1. **账号体系**
   - 用户注册/登录功能
   - Token 认证机制
   - 设备绑定管理

2. **配置同步**
   - 股票列表同步（stock_codes）
   - 备注信息同步（memos）
   - 持仓信息同步（holdings）
   - 预警价格同步（alert_prices）
   - 指数列表同步（index_codes）
   - 置顶股票同步（pinned_stocks，Windows 暂不支持，传空字符串）

3. **同步策略**
   - 首次登录对账机制
   - 自动上传（防抖机制）
   - 手动同步功能
   - 冲突处理（revision 版本控制）

4. **用户体验**
   - 登录界面
   - 账号状态显示
   - 同步状态提示
   - 错误处理与提示

---

## 二、参考 iOS/Mac 实践经验

### 2.1 架构设计参考

#### iOS/Mac 核心组件
1. **AccountApiService** (Swift)
   - 负责所有 API 调用（登录、注册、获取配置、保存配置、绑定设备）
   - Token 管理（Authorization Header）
   - 错误处理统一封装

2. **SyncCoordinator** (Swift)
   - 首次对账逻辑（登录后）
   - 自动上传（防抖 3 秒）
   - 手动同步入口
   - Revision 冲突处理（409 自动重试）

3. **UserSessionManager** (Swift)
   - 会话状态管理
   - Token 持久化（UserDefaults）
   - 登录状态通知

#### 关键实践经验

**1. 首次对账机制（避免误上传）**
```swift
// 登录后先进行首次对账
needInitialSyncCheck = true
performInitialReconcile()

// 对账策略：
// - 云端有配置且哈希不一致 → 弹窗选择（云端覆盖本地 / 本地上传云端 / 取消）
// - 云端无配置或配置为空 → 自动上传本地为初始版本（revision=0）
// - 哈希一致 → 直接锚定，不触发同步
```

**2. 防抖机制（避免频繁上传）**
```swift
// 配置变更后延迟 3 秒上传
debounceTimer = Timer.scheduledTimer(withTimeInterval: 3.0, repeats: false) { [weak self] _ in
    self?.performAutoUploadIfNeeded()
}

// 保护机制：
// - 应用远程配置期间禁止自动上传（isApplyingRemoteConfig）
// - 首次对账未完成时禁止自动上传（needInitialSyncCheck）
```

**3. 冲突处理（Revision 版本控制）**
```swift
// 上传时携带 revision
POST /sync/config { revision: currentRevision, ... }

// 冲突时（409）自动重试
if error.contains("revision_conflict") {
    // 获取最新 revision
    getConfig { latest in
        // 使用最新 revision 重试上传
        uploadLocalConfig(basedOn: latest.revision)
    }
}
```

**4. 哈希计算一致性**
```swift
// 字段顺序必须与服务端一致
let payload = [
    stockCodes ?? "",
    memos ?? "",
    holdings ?? "",
    alertPrices ?? "",
    indexCodes ?? "",
    pinnedStocks ?? ""
].joined(separator: "|")

let hash = SHA256.hash(data: Data(payload.utf8))
```

**5. 空配置判断**
```swift
// 新用户可能返回空配置对象（所有字段都是空字符串）
func isConfigEmpty(_ config: PortfolioConfigDTO) -> Bool {
    let isEmpty = stockCodes.isEmpty && memos.isEmpty && holdings.isEmpty && 
                 alertPrices.isEmpty && indexCodes.isEmpty && pinnedStocks.isEmpty
    return isEmpty
}
```

### 2.2 数据流程

#### 登录流程
```
用户输入账号密码
    ↓
AccountApiService.login()
    ↓
保存 Token 到 UserSessionManager
    ↓
绑定设备（bindDevice）
    ↓
首次对账（performInitialReconcile）
    ↓
根据对账结果决定同步策略
```

#### 配置变更流程
```
用户修改配置（股票列表、持仓等）
    ↓
更新本地 config.xml
    ↓
触发防抖上传（scheduleDebouncedUpload）
    ↓
3 秒后执行自动上传（performAutoUploadIfNeeded）
    ↓
计算哈希，与上次上传哈希对比
    ↓
如果不同，上传到云端（POST /sync/config）
    ↓
保存新的 revision 和 hash
```

#### 同步冲突处理流程
```
上传配置（POST /sync/config）
    ↓
服务端返回 409 revision_conflict
    ↓
获取最新配置（GET /sync/config）
    ↓
使用最新 revision 重试上传
```

---

## 三、iOS/Mac 账号同步实现详解

本章节详细介绍 iOS 和 Mac 应用是如何实现账号同步功能的，包括业务逻辑、技术细节、关键设计决策等，为 Windows 版本的实现提供详细参考。

### 3.1 整体架构

#### 3.1.1 核心组件架构

```
┌─────────────────────────────────────────────────────────┐
│                    iOS/Mac 应用层                        │
├─────────────────────────────────────────────────────────┤
│  UI 层                                                   │
│  ├── AuthView.swift (iOS 登录界面)                      │
│  ├── ViewController.swift (Mac 主控制器)                │
│  └── AccountStatusViewController.swift (账号状态显示)   │
├─────────────────────────────────────────────────────────┤
│  服务层                                                   │
│  ├── UserSessionManager (会话管理)                      │
│  │   ├── iOS: AhFunStockAPP/Services/UserSessionManager │
│  │   └── Mac: AhFunStockShared/Services/UserSessionManager │
│  ├── SyncCoordinator (同步协调器)                       │
│  │   ├── iOS: AhFunStockAPP/Services/SyncCoordinator    │
│  │   └── Mac: ViewController.swift (内联实现)           │
│  └── AccountApiService (API 服务)                       │
│      └── AhFunStockShared/Services/AccountApiService    │
├─────────────────────────────────────────────────────────┤
│  数据层                                                   │
│  ├── SettingsManager (配置管理)                         │
│  │   ├── iOS Core: AhFunStockCore/SettingsManager       │
│  │   └── Shared: AhFunStockShared/SettingsManager       │
│  └── UserDefaults (持久化存储)                          │
└─────────────────────────────────────────────────────────┘
```

#### 3.1.2 组件职责划分

**AccountApiService** (共享服务)
- 位置: `AhFunStockShared/Services/AccountApiService.swift`
- 职责:
  - 封装所有 API 调用（登录、注册、获取配置、保存配置、绑定设备）
  - Token 管理（通过 `UserSessionManager` 获取 Token，添加到 Authorization Header）
  - 错误处理统一封装（返回 `Result<T, AccountApiError>`）
  - 哈希计算（`computeConfigHash` 静态方法）

**UserSessionManager** (会话管理)
- iOS 位置: `AhFunStockAPP/Services/UserSessionManager.swift`
- Mac 共享位置: `AhFunStockShared/Services/UserSessionManager.swift`
- 职责:
  - 管理用户登录状态（`isLoggedIn`, `accountId`, `username`）
  - Token 持久化（UserDefaults）
  - 登录状态变更通知（NotificationCenter）
  - 启动时恢复会话（从 UserDefaults 读取）

**SyncCoordinator** (同步协调器)
- iOS 位置: `AhFunStockAPP/Services/SyncCoordinator.swift` (独立类)
- Mac 位置: `ViewController.swift` (内联实现)
- 职责:
  - 首次对账逻辑（登录后）
  - 自动上传（防抖机制）
  - 手动同步入口
  - 冲突处理（revision 版本控制）

### 3.2 业务逻辑流程

#### 3.2.1 登录流程

**iOS 登录流程**:
```swift
// 1. 用户输入账号密码，点击登录
AuthView.swift: handleAuthContinue()
    ↓
// 2. 调用 AccountApiService.login()
AccountApiService.shared.login(username: password:)
    ↓
// 3. 登录成功后，保存 Token 到 UserSessionManager
UserSessionManager.shared.login(userId: username:)
    ↓
// 4. 绑定设备
bindDeviceAndFinishAuth()
    AccountApiService.shared.bindDevice(machineCode: appType:)
    ↓
// 5. 触发首次对账
SyncCoordinator.shared.onLoginSucceeded()
    performInitialReconcile()
```

**Mac 登录流程**:
```swift
// 1. 用户输入账号密码，点击登录
ViewController.swift: handleAuthContinue()
    ↓
// 2. 调用 AccountApiService.login()
AccountApiService.shared.login(username: password:)
    ↓
// 3. 登录成功后，保存 Token 到 UserSessionManager
UserSessionManager.shared.updateAccountSession(accountId: username: token:)
    ↓
// 4. 绑定设备
bindCurrentDeviceAndFinishAuth()
    AccountApiService.shared.bindDevice(machineCode: appType:)
    ↓
// 5. 触发首次对账
initialSyncAfterLogin()
```

#### 3.2.2 首次对账流程（核心业务逻辑）

首次对账是登录后的关键步骤，用于判断本地配置与云端配置的一致性，决定是否需要同步。

```swift
private func performInitialReconcile() {
    // 步骤 1: 计算本地配置哈希
    let localHash = AccountApiService.computeConfigHash(
        stockCodes: coreS.stockCodes,
        memos: coreS.memos,
        holdings: coreS.holdings,
        alertPrices: coreS.alertPrices,
        indexCodes: coreS.indexCodes,
        pinnedStocks: coreS.pinnedStocks
    )
    
    // 步骤 2: 获取云端配置
    AccountApiService.shared.getConfig { result in
        switch result {
        case .failure:
            // 网络异常：不做自动上传，等待用户手动同步
            needInitialSyncCheck = false
            
        case .success(let remote):
            // 步骤 3: 判断云端配置是否为空
            let isConfigEmpty = remote == nil || isConfigEmpty(remote!)
            
            if let remote = remote, !isConfigEmpty {
                // 步骤 4: 云端有配置，计算云端哈希
                let remoteHash = remote.data_hash ?? 
                    AccountApiService.computeConfigHash(...)
                
                // 步骤 5: 比对哈希
                if localHash == remoteHash {
                    // 哈希一致：直接锚定，不触发同步
                    anchorHash(remoteHash, remote.revision)
                } else {
                    // 哈希不一致：弹窗让用户选择
                    showConflictDialog(localConfig, remote)
                }
            } else {
                // 步骤 6: 云端无配置或配置为空：自动上传本地
                uploadLocalConfigAsInitial()
            }
        }
    }
}
```

**对账策略详解**:

1. **哈希一致** → 直接锚定
   - 说明本地和云端配置完全相同
   - 直接保存哈希和 revision，不触发任何同步操作
   - 避免不必要的网络请求

2. **哈希不一致** → 用户选择
   - 说明本地和云端配置不同
   - 弹窗让用户选择：
     - "云端覆盖本地" → 调用 `applyRemoteConfig()`
     - "本地上传到云端" → 调用 `uploadLocalConfig()`
     - "取消" → 不做任何操作

3. **云端无配置** → 自动上传
   - 新用户或首次登录
   - 自动上传本地配置为初始版本（revision=0）

#### 3.2.3 自动上传流程（防抖机制）

当用户修改配置时，系统会自动上传到云端，但使用防抖机制避免频繁上传。

```swift
// 配置变更时触发
func observeSettingsAndDebounceUpload() {
    // 保护机制：如果正在应用远程配置或首次对账未完成，不触发
    if isApplyingRemoteConfig || needInitialSyncCheck { 
        return 
    }
    
    // 取消之前的定时器
    debounceTimer?.invalidate()
    
    // 创建新的定时器，3 秒后执行
    debounceTimer = Timer.scheduledTimer(withTimeInterval: 3.0, repeats: false) { [weak self] _ in
        self?.performAutoUploadIfNeeded()
    }
}

private func performAutoUploadIfNeeded() {
    // 1. 检查登录状态
    guard UserSessionManager.shared.isLoggedIn else { return }
    
    // 2. 重新计算当前配置哈希
    let currentHash = AccountApiService.computeConfigHash(...)
    
    // 3. 与上次上传的哈希对比
    if currentHash == lastUploadedSettingsHash {
        // 哈希相同，说明没有变更，不需要上传
        return
    }
    
    // 4. 获取当前 revision
    let currentRevision = UserDefaults.standard.object(forKey: "ahfun.sync.lastRevision") as? UInt64 ?? 0
    
    // 5. 上传配置
    uploadLocalConfig(basedOn: currentRevision, isAutoUpload: true)
}
```

**防抖机制的优势**:
- 用户快速连续修改配置时，只上传最后一次修改
- 减少网络请求，节省流量和服务器资源
- 提升用户体验，避免频繁的网络操作

**保护机制**:
- `isApplyingRemoteConfig`: 应用远程配置期间禁止自动上传，避免循环同步
- `needInitialSyncCheck`: 首次对账未完成时禁止自动上传，避免误上传

#### 3.2.4 手动同步流程

用户可以通过 UI 手动触发同步，流程与首次对账类似，但会显示更详细的状态提示。

```swift
func startManualSyncFlow() {
    // 1. 获取云端配置
    AccountApiService.shared.getConfig { result in
        switch result {
        case .failure(let error):
            // 显示错误提示
            showError(error)
            
        case .success(let remote):
            if let remote = remote {
                // 2. 云端有配置：弹窗让用户选择
                showConflictDialog(remote)
            } else {
                // 3. 云端无配置：直接上传本地
                uploadLocalConfigAsInitial()
            }
        }
    }
}
```

#### 3.2.5 冲突处理流程（Revision 版本控制）

当多个设备同时修改配置时，可能发生 revision 冲突。系统会自动处理冲突。

```swift
func uploadLocalConfig(basedOn revision: UInt64) {
    // 1. 构建配置 DTO
    let dto = PortfolioConfigDTO(
        stock_codes: ...,
        revision: revision,
        data_hash: hash,
        ...
    )
    
    // 2. 上传配置
    AccountApiService.shared.saveConfig(config: dto) { result in
        switch result {
        case .success:
            // 3. 上传成功，获取最新配置以获取新的 revision
            AccountApiService.shared.getConfig { configResult in
                if let config = configResult {
                    // 保存新的 revision 和 hash
                    saveRevisionAndHash(config.revision, config.data_hash)
                }
            }
            
        case .failure(let error):
            // 4. 检测 revision 冲突
            if error.contains("revision_conflict") {
                // 5. 获取最新配置
                AccountApiService.shared.getConfig { latestResult in
                    if let latest = latestResult {
                        // 6. 使用最新 revision 重试上传
                        uploadLocalConfig(basedOn: latest.revision)
                    }
                }
            }
        }
    }
}
```

**Revision 版本控制机制**:
- 每次上传配置时，必须携带当前的 revision
- 服务端检查 revision 是否匹配，如果不匹配返回 409 冲突
- 客户端收到冲突后，获取最新 revision 并重试上传
- 确保配置更新的原子性和一致性

### 3.3 技术细节

#### 3.3.1 哈希计算（数据一致性保证）

哈希计算是判断配置是否一致的关键，必须与服务端保持一致。

```swift
public static func computeConfigHash(
    stockCodes: String?,
    memos: String?,
    holdings: String?,
    alertPrices: String?,
    indexCodes: String?,
    pinnedStocks: String?
) -> String {
    // 关键：字段顺序必须与服务端一致
    // 服务端使用 "|" 作为分隔符
    let payload = [
        stockCodes ?? "",
        memos ?? "",
        holdings ?? "",
        alertPrices ?? "",
        indexCodes ?? "",
        pinnedStocks ?? ""
    ].joined(separator: "|")
    
    // 使用 SHA256 计算哈希
    let digest = SHA256.hash(data: Data(payload.utf8))
    
    // 转换为十六进制字符串（小写）
    return digest.compactMap { String(format: "%02x", $0) }.joined()
}
```

**关键要点**:
- 字段顺序必须与服务端完全一致：`stock_codes|memos|holdings|alert_prices|index_codes|pinned_stocks`
- 使用 `|` 作为分隔符（与服务端保持一致）
- 空值使用空字符串 `""`，不使用 `nil`
- 使用 SHA256 算法计算哈希
- 哈希值转换为小写十六进制字符串

#### 3.3.2 Token 管理

Token 用于 API 请求的身份认证，通过 Authorization Header 传递。

```swift
// AccountApiService 中创建带 Token 的请求
private func authorizedRequest(url: URL, method: String = "GET", body: Data? = nil) -> URLRequest {
    var req = URLRequest(url: url)
    req.httpMethod = method
    
    // 从 UserSessionManager 获取 Token
    if let token = UserSessionManager.shared.accountToken, !token.isEmpty {
        req.addValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    }
    
    if body != nil {
        req.addValue("application/json", forHTTPHeaderField: "Content-Type")
    }
    req.httpBody = body
    
    return req
}
```

**Token 持久化**:
```swift
// UserSessionManager 中保存 Token
public func updateAccountSession(accountId: Int, username: String, token: String) {
    defaults.set(accountId, forKey: accountIdKey)
    defaults.set(username, forKey: accountUsernameKey)
    defaults.set(token, forKey: accountTokenKey)  // 保存到 UserDefaults
    NotificationCenter.default.post(name: .accountSessionDidChange, object: nil)
}
```

**Token 过期处理**:
- API 请求返回 401 时，说明 Token 已过期
- 清除本地 Token，提示用户重新登录

#### 3.3.3 配置数据模型

```swift
public struct PortfolioConfigDTO: Codable {
    public let stock_codes: String?      // 股票代码（逗号分隔）
    public let memos: String?            // 备注（管道符分隔）
    public let holdings: String?         // 持仓（逗号分隔，格式：数量*价格）
    public let alert_prices: String?     // 预警价格（逗号分隔）
    public let index_codes: String?      // 指数代码（逗号分隔）
    public let pinned_stocks: String?    // 置顶股票（逗号分隔）
    public let revision: UInt64          // 版本号
    public let data_hash: String?        // 数据哈希
    public let last_client: String?      // 最后更新的客户端类型
}
```

#### 3.3.4 iOS 特殊处理（双 SettingsManager）

iOS 应用存在两个 SettingsManager 实例，使用不同的 UserDefaults 存储：

1. **AhFunStockShared.SettingsManager.shared**
   - 使用: `UserDefaults.standard`
   - 用途: ConfigSync 同步的目标

2. **AhFunStockCore.SettingsManager.sharedCore**
   - 使用: `UserDefaults(suiteName: "group.ahfun.migu.AhFunStockAPP.widget")` (App Group)
   - 用途: iOS 实际使用的配置管理器（Widget 共享）

**关键修复**:
```swift
// 应用远程配置时，必须同时更新两个 SettingsManager
func applyRemoteConfigAndAnchorHash(_ cfg: PortfolioConfigDTO) {
    let m = AhFunStockShared.SettingsManager.shared
    let coreM = AhFunStockCore.SettingsManager.sharedCore
    
    // 同时更新两个 SettingsManager
    m.stockCodes = cfg.stock_codes ?? ""
    coreM.stockCodes = cfg.stock_codes ?? ""
    // ... 其他字段
}

// 上传配置时，优先使用 Core SettingsManager
func uploadLocalConfig() {
    let coreS = AhFunStockCore.SettingsManager.sharedCore
    let sharedS = AhFunStockShared.SettingsManager.shared
    
    // 确保两个 SettingsManager 同步（上传时以 Core 为准）
    sharedS.stockCodes = coreS.stockCodes
    // ... 其他字段
    
    // 使用 Core 配置上传
    let dto = PortfolioConfigDTO(
        stock_codes: coreS.stockCodes,
        // ...
    )
}
```

#### 3.3.5 空配置判断

新用户可能返回空配置对象（所有字段都是空字符串），需要正确判断。

```swift
private func isConfigEmpty(_ config: PortfolioConfigDTO) -> Bool {
    let stockCodes = (config.stock_codes ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    let memos = (config.memos ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    let holdings = (config.holdings ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    let alertPrices = (config.alert_prices ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    let indexCodes = (config.index_codes ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    let pinnedStocks = (config.pinned_stocks ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    
    // 如果所有配置字段都为空，视为空配置
    return stockCodes.isEmpty && memos.isEmpty && holdings.isEmpty && 
           alertPrices.isEmpty && indexCodes.isEmpty && pinnedStocks.isEmpty
}
```

### 3.4 关键设计决策

#### 3.4.1 首次对账机制（避免误上传）

**问题**: 登录后如果立即自动上传本地配置，可能会覆盖云端更新的配置。

**解决方案**: 登录后先进行首次对账，根据对账结果决定是否上传。

**优势**:
- 避免误覆盖云端配置
- 给用户选择权（覆盖或上传）
- 新用户自动上传，老用户智能判断

#### 3.4.2 防抖机制（避免频繁上传）

**问题**: 用户快速连续修改配置时，如果每次都立即上传，会产生大量网络请求。

**解决方案**: 使用防抖机制，配置变更后延迟 3 秒上传。

**优势**:
- 减少网络请求
- 节省流量和服务器资源
- 提升用户体验

#### 3.4.3 Revision 版本控制（冲突处理）

**问题**: 多个设备同时修改配置时，可能发生数据冲突。

**解决方案**: 使用 revision 版本号，每次上传时携带当前 revision，服务端检查是否匹配。

**优势**:
- 确保配置更新的原子性
- 自动处理冲突（获取最新 revision 并重试）
- 保证数据一致性

#### 3.4.4 哈希计算（快速一致性判断）

**问题**: 如何快速判断本地配置与云端配置是否一致？

**解决方案**: 使用 SHA256 计算配置哈希，通过比对哈希快速判断一致性。

**优势**:
- 快速判断（无需逐字段比对）
- 准确性高（哈希冲突概率极低）
- 节省网络流量（只需传输哈希值）

#### 3.4.5 保护机制（避免循环同步）

**问题**: 应用远程配置时，可能会触发自动上传，导致循环同步。

**解决方案**: 使用 `isApplyingRemoteConfig` 标志，应用远程配置期间禁止自动上传。

**优势**:
- 避免循环同步
- 保证数据一致性
- 提升系统稳定性

### 3.5 iOS 和 Mac 的差异

#### 3.5.1 SettingsManager 差异

**iOS**:
- 存在两个 SettingsManager 实例（Shared 和 Core）
- Core 使用 App Group UserDefaults（与 Widget 共享）
- 同步时必须同时更新两个实例

**Mac**:
- 只有一个 SettingsManager 实例（Shared）
- 使用标准 UserDefaults
- 同步时只需更新一个实例

#### 3.5.2 SyncCoordinator 实现差异

**iOS**:
- 独立的 `SyncCoordinator` 类
- 使用 `@MainActor` 确保主线程执行
- 通过 NotificationCenter 通知 UI 更新

**Mac**:
- 内联在 `ViewController` 中实现
- 直接调用 UI 更新方法
- 使用 `logInfo()` 记录日志

#### 3.5.3 UI 交互差异

**iOS**:
- 使用 SwiftUI 的 `AuthView` 作为登录界面
- 使用 Toast 提示同步状态
- 通过 NotificationCenter 通知 UI 更新

**Mac**:
- 使用 AppKit 的 `NSPanel` 作为登录界面
- 使用 `NSAlert` 显示提示和选择对话框
- 直接调用 UI 更新方法

### 3.6 错误处理

#### 3.6.1 网络错误

```swift
case .networkError(let description):
    // 网络异常：不做自动上传，等待用户手动同步
    needInitialSyncCheck = false
    print("❌ [ConfigSync] 首次对账失败：网络异常")
```

#### 3.6.2 Token 过期

```swift
if http.statusCode == 401 {
    // Token 过期：清除本地 Token，提示重新登录
    UserSessionManager.shared.clearAccountSession()
    completion(.failure(.unauthorized))
}
```

#### 3.6.3 Revision 冲突

```swift
if case .serverError(let msg) = error, msg.contains("revision_conflict") {
    // 获取最新配置
    AccountApiService.shared.getConfig { latest in
        // 使用最新 revision 重试上传
        uploadLocalConfig(basedOn: latest.revision)
    }
}
```

### 3.7 数据持久化

#### 3.7.1 UserDefaults 键名

```swift
// 账号信息
"ahfun.account.id"          // 账号 ID
"ahfun.account.username"    // 用户名
"ahfun.account.token"       // Token

// 同步状态
"ahfun.sync.lastHash"       // 上次上传的哈希
"ahfun.sync.lastRevision"   // 上次的 revision
"ahfun.sync.lastTime"       // 上次同步时间

// 设备信息
"machineCode"               // 设备机器码
```

#### 3.7.2 配置数据存储

- **iOS**: 使用 `SettingsManager` 存储配置，底层使用 UserDefaults
- **Mac**: 使用 `SettingsManager` 存储配置，底层使用 UserDefaults

### 3.8 总结

iOS 和 Mac 应用的账号同步实现具有以下特点：

1. **架构清晰**: 职责分离，AccountApiService、UserSessionManager、SyncCoordinator 各司其职
2. **业务逻辑完善**: 首次对账、自动上传、手动同步、冲突处理等流程完整
3. **技术细节到位**: 哈希计算、Token 管理、Revision 版本控制等实现规范
4. **用户体验良好**: 防抖机制、保护机制、错误处理等提升用户体验
5. **可维护性强**: 代码结构清晰，注释详细，易于维护和扩展

这些实践经验为 Windows 版本的实现提供了宝贵的参考，Windows 版本应该遵循相同的架构设计和业务逻辑，确保跨平台的一致性。

---

## 四、Windows 应用现状分析

### 4.1 现有架构

#### 配置存储
- **存储方式**: XML 文件（config.xml）
- **存储位置**: `%AppData%\{CompanyName}\{ProductName}\config.xml`
- **管理类**: `XMLHandler.vb`
- **配置字段**:
  - `StockCode`: 股票代码（逗号分隔）
  - `Memo`: 备注（管道符分隔）
  - `IndexCode`: 指数代码（逗号分隔）
  - `MyHolding`: 持仓（逗号分隔，格式：数量*价格）
  - `AlertPrice`: 预警价格（逗号分隔）
  - UI 配置：`OpacityLevel`, `Style`, `Columns`, `Bosskey`, `Detail`, `AutoStart`, `TopMost`, `AutoHide`, `BackgroundTransparent`

#### API 服务
- **现有类**: `UserApiService.vb`
- **现有功能**:
  - `AddUser()`: 游客模式用户注册
  - `AddUserData()`: 用户数据上报
  - `AddErrorLog()`: 错误日志上报
  - `AddUserAction()`: 用户行为记录
  - `AddLogs()`: 批量日志上报
- **API 基础 URL**: 
  - 生产环境: `https://api.ahfun.me`
  - 测试环境: `http://127.0.0.1:5000`
- **配置位置**: `MdlConstant.vb` 中的 `strAhFunLogAPI_P` 和 `strAhFunLogAPI_T`

#### 数据流程
```
应用启动
    ↓
读取 config.xml（XMLHandler）
    ↓
加载股票数据（FrmStock.vb）
    ↓
定时刷新数据（BackgroundTask.vb）
    ↓
用户修改配置（FrmOption.vb）
    ↓
保存到 config.xml
```

### 3.2 技术栈
- **语言**: VB.NET
- **框架**: .NET Framework（Windows Forms）
- **HTTP 客户端**: `System.Net.Http.HttpClient`
- **JSON 序列化**: `Newtonsoft.Json`
- **配置管理**: XML + `My.Settings`

### 3.3 需要改造的部分
1. **扩展 UserApiService.vb**
   - 添加账号认证相关方法
   - 添加配置同步相关方法
   - 添加 Token 管理

2. **新建服务类**
   - `UserSessionManager.vb`: 会话管理
   - `SyncCoordinator.vb`: 同步协调器

3. **扩展配置管理**
   - 配置字段映射（Windows → API）
   - 配置变更监听
   - 同步状态管理

4. **UI 改造**
   - 新建登录界面（`FrmLogin.vb`）
   - 在设置界面添加账号状态显示
   - 添加同步状态提示

---

## 四、架构设计

### 4.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    Windows 应用层                        │
├─────────────────────────────────────────────────────────┤
│  UI 层                                                   │
│  ├── FrmLogin.vb (登录界面)                             │
│  ├── FrmOption.vb (设置界面 - 账号状态显示)             │
│  └── FrmStock.vb (主界面 - 配置变更监听)                │
├─────────────────────────────────────────────────────────┤
│  服务层                                                   │
│  ├── UserSessionManager.vb (会话管理)                   │
│  ├── SyncCoordinator.vb (同步协调器)                    │
│  └── AccountApiService.vb (API 服务 - 扩展)             │
├─────────────────────────────────────────────────────────┤
│  数据层                                                   │
│  ├── XMLHandler.vb (本地配置管理)                       │
│  └── My.Settings (Token 持久化)                         │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                    API 服务层                            │
│  ├── POST /auth/register (注册)                         │
│  ├── POST /auth/login (登录)                            │
│  ├── POST /auth/bind_device (绑定设备)                  │
│  ├── GET /sync/config (获取配置)                        │
│  ├── POST /sync/config (保存配置)                       │
│  └── GET /sync/version (获取版本)                       │
└─────────────────────────────────────────────────────────┘
```

### 4.2 核心组件设计

#### 4.2.1 UserSessionManager.vb
```vb
Public Class UserSessionManager
    ' 单例模式
    Public Shared ReadOnly Instance As New UserSessionManager()
    
    ' 属性
    Public Property IsLoggedIn As Boolean
    Public Property AccountId As Integer?
    Public Property Username As String
    Public Property Token As String
    
    ' 方法
    Public Sub Login(accountId As Integer, username As String, token As String)
    Public Sub Logout()
    Public Function GetToken() As String
    Public Sub SaveToken(token As String)
    Public Sub LoadToken()
End Class
```

**职责**:
- 管理用户登录状态
- Token 的持久化（My.Settings）
- 登录状态变更通知（事件）

#### 4.2.2 AccountApiService.vb (扩展)
```vb
Public Class AccountApiService
    ' 账号认证
    Public Function Login(username As String, password As String) As Task(Of LoginResult)
    Public Function Register(username As String, password As String, email As String) As Task(Of RegisterResult)
    Public Function BindDevice(machineCode As String, appType As String) As Task(Of Boolean)
    Public Function Logout() As Task(Of Boolean)
    
    ' 配置同步
    Public Function GetConfig() As Task(Of PortfolioConfig)
    Public Function SaveConfig(config As PortfolioConfig, revision As ULong) As Task(Of SaveConfigResult)
    Public Function GetVersion() As Task(Of VersionInfo)
    
    ' 工具方法
    Private Function MakeAuthorizedRequest(url As String, method As String, body As Object) As HttpRequestMessage
    Public Shared Function ComputeConfigHash(config As PortfolioConfig) As String
End Class
```

**职责**:
- 封装所有 API 调用
- Token 管理（Authorization Header）
- 错误处理统一封装
- 哈希计算

#### 4.2.3 SyncCoordinator.vb
```vb
Public Class SyncCoordinator
    ' 单例模式
    Public Shared ReadOnly Instance As New SyncCoordinator()
    
    ' 状态
    Private needInitialSyncCheck As Boolean = False
    Private isApplyingRemoteConfig As Boolean = False
    Private lastUploadedHash As String = ""
    Private debounceTimer As Timer
    
    ' 方法
    Public Sub OnLoginSucceeded()
    Public Sub OnConfigChanged()
    Public Sub PerformManualSync()
    
    ' 私有方法
    Private Sub PerformInitialReconcile()
    Private Sub ScheduleDebouncedUpload()
    Private Sub PerformAutoUploadIfNeeded()
    Private Sub ApplyRemoteConfig(config As PortfolioConfig)
    Private Function IsConfigEmpty(config As PortfolioConfig) As Boolean
End Class
```

**职责**:
- 首次对账逻辑
- 自动上传（防抖）
- 手动同步
- 冲突处理

### 4.3 数据模型

#### PortfolioConfig (配置数据模型)
```vb
Public Class PortfolioConfig
    Public Property StockCodes As String
    Public Property Memos As String
    Public Property Holdings As String
    Public Property AlertPrices As String
    Public Property IndexCodes As String
    Public Property PinnedStocks As String
    Public Property Revision As ULong
    Public Property DataHash As String
    Public Property LastClient As String
End Class
```

#### 配置字段映射
| Windows (config.xml) | API 字段 | 说明 |
|---------------------|---------|------|
| StockCode | stock_codes | 股票代码（逗号分隔） |
| Memo | memos | 备注（管道符分隔） |
| IndexCode | index_codes | 指数代码（逗号分隔） |
| MyHolding | holdings | 持仓（逗号分隔，格式：数量*价格） |
| AlertPrice | alert_prices | 预警价格（逗号分隔） |
| - | pinned_stocks | 置顶股票（Windows 暂不支持，传空字符串） |

**注意**: Windows 的 UI 配置（OpacityLevel、Style、Columns 等）不参与云端同步，仅本地存储。

---

## 五、实现计划

### 5.1 阶段一：基础服务层（预计 2-3 天）

#### 任务 1.1: 扩展 UserApiService.vb
- [ ] 添加账号认证方法
  - `Login(username, password)`: 登录并获取 Token
  - `Register(username, password, email)`: 注册账号
  - `BindDevice(machineCode, appType)`: 绑定设备
  - `Logout()`: 注销登录
- [ ] 添加配置同步方法
  - `GetConfig()`: 获取云端配置
  - `SaveConfig(config, revision)`: 保存配置到云端
  - `GetVersion()`: 获取配置版本信息
- [ ] 添加 Token 管理
  - `MakeAuthorizedRequest()`: 创建带 Token 的请求
  - Token 从 `UserSessionManager` 获取
- [ ] 添加哈希计算
  - `ComputeConfigHash()`: 计算配置哈希（SHA256）
  - 字段顺序：`stock_codes|memos|holdings|alert_prices|index_codes|pinned_stocks`

**技术要点**:
- 使用 `HttpClient` 进行异步请求
- 使用 `Newtonsoft.Json` 进行 JSON 序列化/反序列化
- Token 通过 `Authorization: Bearer {token}` Header 传递
- 错误处理统一封装，返回 `Result` 类型

#### 任务 1.2: 新建 UserSessionManager.vb
- [ ] 实现单例模式
- [ ] 实现登录/登出方法
- [ ] 实现 Token 持久化（My.Settings）
- [ ] 实现登录状态变更事件
- [ ] 启动时自动加载 Token

**技术要点**:
- 使用 `My.Settings` 持久化 Token
- 使用事件通知登录状态变更
- 启动时检查 Token 有效性（可选）

### 5.2 阶段二：同步协调层（预计 2-3 天）

#### 任务 2.1: 新建 SyncCoordinator.vb
- [ ] 实现首次对账逻辑
  - `OnLoginSucceeded()`: 登录成功后触发
  - `PerformInitialReconcile()`: 执行首次对账
  - 对账策略：
    - 云端有配置且哈希不一致 → 弹窗选择
    - 云端无配置或配置为空 → 自动上传本地
    - 哈希一致 → 直接锚定
- [ ] 实现自动上传（防抖）
  - `OnConfigChanged()`: 配置变更时触发
  - `ScheduleDebouncedUpload()`: 防抖延迟 3 秒
  - `PerformAutoUploadIfNeeded()`: 执行自动上传
  - 保护机制：应用远程配置期间禁止自动上传
- [ ] 实现手动同步
  - `PerformManualSync()`: 手动同步入口
  - 支持强制同步（忽略本地哈希）
- [ ] 实现冲突处理
  - 检测 409 revision_conflict 错误
  - 自动获取最新 revision 并重试
- [ ] 实现空配置判断
  - `IsConfigEmpty()`: 判断配置是否为空

**技术要点**:
- 使用 `Timer` 实现防抖
- 使用 `Task` 进行异步操作
- 哈希计算与 iOS/Mac 保持一致
- 详细的日志记录

### 5.3 阶段三：配置集成层（预计 2 天）

#### 任务 3.1: 配置适配器
- [ ] 创建配置映射方法
  - `ConfigToApiModel()`: Windows 配置 → API 模型
  - `ApiModelToConfig()`: API 模型 → Windows 配置
- [ ] 扩展 XMLHandler.vb（可选）
  - 添加批量更新方法
  - 添加配置变更事件

#### 任务 3.2: 配置变更监听
- [ ] 在 `FrmOption.vb` 中集成
  - 保存配置时触发 `SyncCoordinator.OnConfigChanged()`
- [ ] 在 `FrmStock.vb` 中集成
  - 股票操作（添加/删除/修改）时触发同步
- [ ] 确保不触发循环同步
  - 应用远程配置时不触发自动上传

### 5.4 阶段四：UI 集成层（预计 3-4 天）

#### 任务 4.1: 登录界面（FrmLogin.vb）
- [ ] 设计登录界面
  - 用户名/密码输入框
  - 登录/注册切换
  - 记住用户名（可选）
  - 错误提示区域
- [ ] 实现登录逻辑
  - 调用 `AccountApiService.Login()`
  - 成功后保存 Token 并关闭窗口
  - 失败时显示错误提示
- [ ] 实现注册逻辑
  - 调用 `AccountApiService.Register()`
  - 注册成功后自动登录

#### 任务 4.2: 账号状态显示（FrmOption.vb）
- [ ] 添加账号状态区域
  - 显示登录状态（已登录/未登录）
  - 显示用户名
  - 显示账号 ID（可选）
- [ ] 添加操作按钮
  - "登录"按钮（未登录时）
  - "同步数据"按钮（已登录时）
  - "注销账号"按钮（已登录时）
- [ ] 实现同步状态提示
  - 同步成功提示
  - 同步失败提示
  - 首次对账冲突弹窗

#### 任务 4.3: 同步状态提示
- [ ] 实现 Toast 提示（可选）
  - 同步成功提示
  - 同步失败提示
- [ ] 实现冲突处理弹窗
  - 云端覆盖本地
  - 本地上传到云端
  - 取消操作

---

## 六、技术要点

### 6.1 哈希计算一致性

**关键**: 必须与 iOS/Mac 和服务端保持一致

```vb
Public Shared Function ComputeConfigHash(config As PortfolioConfig) As String
    ' 字段顺序必须与服务端一致：stock_codes|memos|holdings|alert_prices|index_codes|pinned_stocks
    Dim payload As String = String.Join("|", {
        If(config.StockCodes, ""),
        If(config.Memos, ""),
        If(config.Holdings, ""),
        If(config.AlertPrices, ""),
        If(config.IndexCodes, ""),
        If(config.PinnedStocks, "")
    })
    
    ' 使用 SHA256 计算哈希
    Using sha256 As New System.Security.Cryptography.SHA256Managed()
        Dim hashBytes As Byte() = sha256.ComputeHash(System.Text.Encoding.UTF8.GetBytes(payload))
        Return BitConverter.ToString(hashBytes).Replace("-", "").ToLower()
    End Using
End Function
```

### 6.2 Revision 版本控制

**首次上传**:
```vb
' 首次上传使用 revision=0
Dim result = Await AccountApiService.SaveConfig(config, 0)
```

**后续上传**:
```vb
' 使用上次获取的 revision+1
Dim currentRevision = GetLastRevision() ' 从 My.Settings 或本地变量获取
Dim result = Await AccountApiService.SaveConfig(config, currentRevision)
```

**冲突处理**:
```vb
Try
    Dim result = Await AccountApiService.SaveConfig(config, currentRevision)
Catch ex As ApiException When ex.StatusCode = 409
    ' 获取最新配置
    Dim latestConfig = Await AccountApiService.GetConfig()
    ' 使用最新 revision 重试
    Dim retryResult = Await AccountApiService.SaveConfig(config, latestConfig.Revision)
End Try
```

### 6.3 首次对账策略

```vb
Private Async Sub PerformInitialReconcile()
    ' 1. 计算本地配置哈希
    Dim localConfig = LoadLocalConfig()
    Dim localHash = AccountApiService.ComputeConfigHash(localConfig)
    
    ' 2. 获取云端配置
    Dim remoteConfig = Await AccountApiService.GetConfig()
    
    ' 3. 判断策略
    If remoteConfig Is Nothing OrElse IsConfigEmpty(remoteConfig) Then
        ' 云端无配置：自动上传本地
        Await UploadLocalConfigAsInitial()
    Else
        ' 计算云端哈希
        Dim remoteHash = remoteConfig.DataHash
        
        If localHash = remoteHash Then
            ' 哈希一致：直接锚定
            AnchorHash(remoteHash, remoteConfig.Revision)
        Else
            ' 哈希不一致：弹窗选择
            ShowConflictDialog(localConfig, remoteConfig)
        End If
    End If
End Sub
```

### 6.4 防抖机制

```vb
Private debounceTimer As Timer

Private Sub OnConfigChanged()
    ' 如果正在应用远程配置，不触发自动上传
    If isApplyingRemoteConfig OrElse needInitialSyncCheck Then
        Return
    End If
    
    ' 取消之前的定时器
    If debounceTimer IsNot Nothing Then
        debounceTimer.Stop()
        debounceTimer.Dispose()
    End If
    
    ' 创建新的定时器，3 秒后执行
    debounceTimer = New Timer(AddressOf PerformAutoUploadIfNeeded, Nothing, 3000, Timeout.Infinite)
End Sub
```

### 6.5 Token 管理

**保存 Token**:
```vb
' 保存到 My.Settings
My.Settings.AccountToken = token
My.Settings.AccountId = accountId
My.Settings.Username = username
My.Settings.Save()
```

**使用 Token**:
```vb
Private Function MakeAuthorizedRequest(url As String, method As String, body As Object) As HttpRequestMessage
    Dim request As New HttpRequestMessage(New HttpMethod(method), url)
    
    ' 添加 Token
    Dim token = UserSessionManager.Instance.GetToken()
    If Not String.IsNullOrEmpty(token) Then
        request.Headers.Authorization = New AuthenticationHeaderValue("Bearer", token)
    End If
    
    ' 添加 Body
    If body IsNot Nothing Then
        Dim json = JsonConvert.SerializeObject(body)
        request.Content = New StringContent(json, Encoding.UTF8, "application/json")
    End If
    
    Return request
End Function
```

### 6.6 异步操作处理

**使用 Async/Await**:
```vb
Public Async Function Login(username As String, password As String) As Task(Of LoginResult)
    Try
        Dim request = MakeLoginRequest(username, password)
        Dim response = Await httpClient.SendAsync(request)
        Dim content = Await response.Content.ReadAsStringAsync()
        
        If response.IsSuccessStatusCode Then
            Dim result = JsonConvert.DeserializeObject(Of LoginResponse)(content)
            Return New LoginResult With {.Success = True, .Token = result.Token, .AccountId = result.AccountId}
        Else
            Return New LoginResult With {.Success = False, .ErrorMessage = "登录失败"}
        End If
    Catch ex As Exception
        Return New LoginResult With {.Success = False, .ErrorMessage = ex.Message}
    End Try
End Function
```

**UI 线程调用**:
```vb
' 在 UI 事件处理中
Private Async Sub btnLogin_Click(sender As Object, e As EventArgs) Handles btnLogin.Click
    btnLogin.Enabled = False
    Try
        Dim result = Await AccountApiService.Login(txtUsername.Text, txtPassword.Text)
        If result.Success Then
            UserSessionManager.Instance.Login(result.AccountId, txtUsername.Text, result.Token)
            Me.DialogResult = DialogResult.OK
            Me.Close()
        Else
            MessageBox.Show(result.ErrorMessage, "登录失败", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End If
    Finally
        btnLogin.Enabled = True
    End Try
End Sub
```

---

## 七、兼容性考虑

### 7.1 向后兼容

#### 未登录用户
- 继续使用本地 `config.xml` 存储配置
- 不影响现有功能
- 可以随时登录启用云端同步

#### 已登录用户
- 启用云端同步功能
- 本地配置与云端配置保持一致
- 登出后恢复本地模式

### 7.2 数据迁移

#### 首次登录
- 自动上传本地配置到云端
- 保留本地 `config.xml` 作为备份
- UI 配置（OpacityLevel、Style 等）不参与同步

#### 云端配置覆盖本地
- 只覆盖同步字段（StockCode、Memo、IndexCode、MyHolding、AlertPrice）
- 保留 UI 配置（OpacityLevel、Style、Columns 等）
- 保留窗口位置等本地设置

### 7.3 错误处理

#### 网络异常
- 不影响本地使用
- 显示友好的错误提示
- 记录详细日志便于排查

#### Token 过期
- 检测 401 错误
- 提示用户重新登录
- 清除本地 Token

#### 同步失败
- 显示明确的错误提示
- 提供重试机制
- 记录失败原因

---

## 八、API 接口规范

### 8.1 认证接口

#### POST /auth/register
**请求**:
```json
{
  "username": "demo_user",
  "password": "password123",
  "email": "demo@example.com",
  "mobile_phone": "13100000000"
}
```

**响应**:
```json
{
  "message": "Registration successful",
  "account": {
    "account_id": 1,
    "username": "demo_user"
  },
  "token": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "expires_at": "2025-02-15T10:30:00Z"
  }
}
```

#### POST /auth/login
**请求**:
```json
{
  "username": "demo_user",
  "password": "password123"
}
```

**响应**: 同 `/auth/register`

#### POST /auth/bind_device
**请求**:
```json
{
  "machine_code": "device-uuid",
  "app_type": "AhFunStock_Win"
}
```

**响应**:
```json
{
  "message": "Device bound successfully"
}
```

#### POST /auth/logout
**请求**: 无 Body，需要 Token

**响应**:
```json
{
  "message": "Logout successful"
}
```

### 8.2 配置同步接口

#### GET /sync/config
**请求**: 无 Body，需要 Token

**响应**:
```json
{
  "account_id": 1,
  "config": {
    "stock_codes": "sh600001,sz000001",
    "memos": "备注1|备注2",
    "holdings": "100*10.5,200*20.3",
    "alert_prices": "11/12/13,21/22/23",
    "index_codes": "sh000001,sz399001",
    "pinned_stocks": "sh600001",
    "revision": 5,
    "data_hash": "abc123...",
    "last_client": "AhFunStock_Win"
  },
  "revision": 5
}
```

**注意**: 新用户可能返回 `config: null`

#### POST /sync/config
**请求**:
```json
{
  "stock_codes": "sh600001,sz000001",
  "memos": "备注1|备注2",
  "holdings": "100*10.5,200*20.3",
  "alert_prices": "11/12/13,21/22/23",
  "index_codes": "sh000001,sz399001",
  "pinned_stocks": "sh600001",
  "revision": 5,
  "data_hash": "abc123...",
  "last_client": "AhFunStock_Win"
}
```

**响应（成功）**:
```json
{
  "message": "Config saved successfully",
  "config": {
    "stock_codes": "sh600001,sz000001",
    "memos": "备注1|备注2",
    "holdings": "100*10.5,200*20.3",
    "alert_prices": "11/12/13,21/22/23",
    "index_codes": "sh000001,sz399001",
    "pinned_stocks": "sh600001",
    "revision": 6,
    "data_hash": "def456...",
    "last_client": "AhFunStock_Win"
  }
}
```

**响应（冲突 409）**:
```json
{
  "message": "revision_conflict",
  "latest": {
    "stock_codes": "sh600001,sz000001,sh600002",
    "revision": 7,
    "data_hash": "ghi789..."
  }
}
```

#### GET /sync/version
**请求**: 无 Body，需要 Token

**响应**:
```json
{
  "revision": 7,
  "updated_at": "2025-01-15T10:30:00Z"
}
```

---

## 九、测试计划

### 9.1 单元测试

#### AccountApiService 测试
- [ ] 登录成功/失败场景
- [ ] 注册成功/失败场景
- [ ] Token 管理测试
- [ ] 哈希计算一致性测试
- [ ] 错误处理测试

#### SyncCoordinator 测试
- [ ] 首次对账逻辑测试
- [ ] 防抖机制测试
- [ ] 冲突处理测试
- [ ] 空配置判断测试

### 9.2 集成测试

#### 登录流程测试
- [ ] 新用户注册 → 登录 → 首次对账
- [ ] 已登录用户登录 → 首次对账
- [ ] Token 过期处理

#### 同步流程测试
- [ ] 本地修改 → 自动上传
- [ ] 云端修改 → 拉取配置
- [ ] 冲突场景处理
- [ ] 网络异常处理

### 9.3 兼容性测试

#### 向后兼容
- [ ] 未登录用户正常使用
- [ ] 已登录用户登出后正常使用
- [ ] 旧版本配置文件兼容

#### 跨平台同步
- [ ] Windows → iOS 同步
- [ ] Windows → Mac 同步
- [ ] iOS → Windows 同步
- [ ] Mac → Windows 同步

### 9.4 性能测试

#### 同步性能
- [ ] 配置上传耗时
- [ ] 配置下载耗时
- [ ] 防抖机制有效性

#### 内存占用
- [ ] 登录状态管理内存占用
- [ ] 同步协调器内存占用

---

## 十、风险评估与应对

### 10.1 技术风险

#### 风险 1: 哈希计算不一致
**影响**: 导致误判配置不一致，触发不必要的同步
**应对**: 
- 严格按照服务端字段顺序实现
- 编写单元测试验证哈希一致性
- 与 iOS/Mac 实现对比验证

#### 风险 2: 异步操作线程安全问题
**影响**: UI 更新可能不在主线程，导致异常
**应对**:
- 使用 `Invoke` 确保 UI 更新在主线程
- 使用 `Async/Await` 简化异步操作
- 充分测试各种场景

#### 风险 3: Token 过期处理
**影响**: 用户操作中断，体验不佳
**应对**:
- 检测 401 错误并提示重新登录
- 自动清除过期 Token
- 提供友好的错误提示

### 10.2 业务风险

#### 风险 1: 配置丢失
**影响**: 用户数据丢失
**应对**:
- 本地配置始终保留作为备份
- 同步前进行数据验证
- 提供数据恢复机制

#### 风险 2: 同步冲突处理不当
**影响**: 用户数据被错误覆盖
**应对**:
- 实现完善的冲突处理机制
- 提供用户选择（覆盖/上传/取消）
- 记录详细的操作日志

### 10.3 兼容性风险

#### 风险 1: 旧版本用户升级问题
**影响**: 升级后功能异常
**应对**:
- 保持向后兼容
- 提供平滑升级路径
- 充分测试升级场景

---

## 十一、实施时间表

### 第一阶段：基础服务层（2-3 天）
- Day 1: 扩展 UserApiService.vb，实现账号认证方法
- Day 2: 新建 UserSessionManager.vb，实现会话管理
- Day 3: 测试和调试基础服务层

### 第二阶段：同步协调层（2-3 天）
- Day 1: 新建 SyncCoordinator.vb，实现首次对账逻辑
- Day 2: 实现自动上传和防抖机制
- Day 3: 实现冲突处理和测试

### 第三阶段：配置集成层（2 天）
- Day 1: 实现配置适配器
- Day 2: 集成配置变更监听

### 第四阶段：UI 集成层（3-4 天）
- Day 1-2: 实现登录界面（FrmLogin.vb）
- Day 3: 在设置界面添加账号状态显示
- Day 4: 实现同步状态提示和测试

### 第五阶段：测试和优化（2-3 天）
- Day 1: 单元测试和集成测试
- Day 2: 兼容性测试和跨平台同步测试
- Day 3: 性能优化和 Bug 修复

**总计**: 11-15 个工作日（约 2-3 周）

---

## 十二、后续优化方向

### 12.1 功能增强
- [ ] 支持多账号切换
- [ ] 支持配置历史版本回滚
- [ ] 支持配置导出/导入
- [ ] 支持离线模式（队列同步）

### 12.2 性能优化
- [ ] 增量同步（只同步变更部分）
- [ ] 压缩传输（大数据量场景）
- [ ] 本地缓存优化

### 12.3 用户体验优化
- [ ] 同步进度显示
- [ ] 同步状态图标（托盘图标）
- [ ] 自动同步开关
- [ ] 同步频率设置

---

## 十三、参考资料

### 13.1 iOS/Mac 实现参考
- `AhFunStockShared/Services/AccountApiService.swift`: API 服务实现
- `AhFunStockAPP/Services/SyncCoordinator.swift`: 同步协调器实现
- `AhFunStockAPP/Services/UserSessionManager.swift`: 会话管理实现
- `AhFunStockMac/ViewController.swift`: Mac 端集成示例

### 13.2 API 文档
- `AhFunStokAPI/docs/README.md`: API 接口文档
- `AhFunStokAPI/app.py`: 服务端实现参考

### 13.3 Windows 应用代码
- `AhFunStock_Win/UserApiService.vb`: 现有 API 服务
- `AhFunStock_Win/XMLHandler.vb`: 配置管理
- `AhFunStock_Win/FrmOption.vb`: 设置界面
- `AhFunStock_Win/FrmStock.vb`: 主界面

---

## 十四、总结

本文档详细描述了 Windows 版本应用增加账号同步功能的需求和实现计划。通过参考 iOS/Mac 应用的实践经验，结合 Windows 程序的特点，给出了可靠的实施方案。

**核心要点**:
1. **架构一致性**: 与 iOS/Mac 保持架构一致，便于维护和扩展
2. **向后兼容**: 确保未登录用户正常使用，不影响现有功能
3. **可靠性**: 完善的错误处理和冲突处理机制
4. **用户体验**: 友好的 UI 和清晰的状态提示

**实施建议**:
- 按照阶段逐步实施，每个阶段完成后进行测试
- 充分参考 iOS/Mac 的实现，避免重复踩坑
- 注重细节，特别是哈希计算和版本控制
- 充分测试，特别是跨平台同步场景

---

**文档维护**: 本文档应随着实施进度持续更新，记录实际遇到的问题和解决方案。

