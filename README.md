# UniXNU-sweet: Xiaomi Redmi Note 10 Pro (sweet / SM7150) Device Repository

本倉庫為 **Xiaomi Redmi Note 10 Pro** (`sweet` / Qualcomm Snapdragon 732G - SM7150) 的官方標準 UniXNU 設備定義倉庫。

## 硬體基本資訊
- **SoC**：Qualcomm SM7150 (Kryo 470 2x Gold + 6x Silver)
- **GPU**：Adreno 618 (A6xx 系列)
- **存儲**：UFS 2.1 (UFSHCI 2.1 @ `0x01d84000`)
- **顯示**：6.67" AMOLED 1080x2400 @ 60/120Hz (Continuous-Splash GOP @ `0x9c000000`)
- **觸控**：Goodix GT9896 (Yellowstone 協議 @ QUPv3 SE7 `0x00a84000`)
- **電源與按鍵**：PM6150 (PON Power / VolDown) + PM6150L (GPIO VolUp)
- **目標系統**：iOS 16.7.16 (Build `20H392` / Profile `d22ap` - iPhone X)

## 倉庫結構
- `board.toml`：板級配置描述（IPSW 元數據、分區幾何、核心參數與引導規格）
- `configs/sweet_defconfig`：板級 XNU 核心配置
- `dts/`：設備樹原始碼與疊加定義
- `drivers/`：專屬 XNU 驅動模組
- `kits/`：內核套件庫
- `patches/`：設備專屬補丁鏈
- `scripts/`：構建與引導生成腳本（含 `make-sweet-adt.py`）

詳細硬體規格手冊請參閱根目錄下的 [`SWEET_HARDWARE_SPEC.md`](../SWEET_HARDWARE_SPEC.md)。
