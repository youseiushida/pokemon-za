# ポケモン
図鑑番号: int 同じ図鑑番号の別のポケモンもいることに注意
名前: str
タイプ: list[str]
入手方法: str
HP種族値: int
こうげき種族値: int
ぼうぎょ種族値: int
とくこう種族値: int
とくぼう種族値: int
すばやさ種族値: int
種族値合計: int
# 技
名前: str
説明: str
タイプ: str
分類: str (変化, 物理, 特殊)
威力: int
発動時間[s]: float
発生まで[s]: float
発生まで（せんせいのツメ）[s]: float
硬直時間[s]: float
全体時間[s]: float
DPS: float
直接攻撃: str
ゆびをふる: str
まもる: str
みがわり: str
範囲: str
効果: str
# ポケモン-技
覚え方: list[str] (レベル, 技マシン)
レベル: int
技マシン番号: int
