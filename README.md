# 8BitDo Micro Remapper

USB 接続した **8BitDo Micro** のボタンを、キーボードやマウスの入力に割り当てるデスクトップアプリです。
**Windows と macOS** で同じように使えます。

- Micro の形を画面に表示し、ボタンをクリックするだけで割り当てられます
- 割り当て方は 2 通り：**実際にキーを押して登録**（`Ctrl+C` のような組み合わせも可）、または**一覧から選択**
- コントローラーを押すと、画面上の同じボタンが光ります（接続や割り当てのチェックに使えます）
- キーボード / マウス（クリック・ホイール・カーソル移動）/ 文字列入力 / 無効 を割り当て可能
- プロファイル（JSON）の保存・切り替え・インポート・エクスポート
- このアプリのウィンドウが前面になくても動きます

## 必要なもの

- Python 3.9 以上（tkinter 付き。python.org のインストーラ版なら同梱されています）
- 8BitDo Micro（USB-C ケーブルで接続）

## インストールと起動

```bash
cd 8bitdo-controller
python3 -m venv .venv
# macOS
source .venv/bin/activate
# Windows (PowerShell)
# .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m remapper
```

## コントローラーの準備

Micro 背面のモードスイッチを **ゲームパッドモード（D または S）** にしてから USB で接続します。
**K（キーボードモード）では使えません。** K モードの Micro は自分でキーを送るため、
本物のキーボードと区別できないからです。

## 使い方

1. 画面上のボタン（または下の一覧の行）をクリックして選びます。選んだボタンはオレンジの枠になります。
2. 右のパネルで割り当てます。
   - **「⌨ キーを押して設定」** を押してから、割り当てたいキーを押します。修飾キーと組み合わせれば
     （例：`Ctrl` を押したまま `C`）組み合わせごと登録されます。修飾キーを 1 つだけ押して離すと、その修飾キーだけが登録されます。
   - **一覧から選択**：修飾キーのチェックボックスとキーのプルダウンで選びます。
   - **マウス**：左/右/中クリック、ホイール、カーソル移動の中から選びます。
   - **文字列入力**：ボタンを押すと、決めておいた文字列を入力します。
3. 変更はすぐに反映され、自動で保存されます。

上の **「リマップ有効」** を外すと、一時的に割り当てを止められます。

### ボタンが光らない・別のボタンが光るとき

接続モードや OS によって、コントローラーから届くボタンの番号が違うことがあります。
**「Fix all」** を押し、画面の指示どおりにボタンを順番に押してください（1 回で済みます）。
1 つだけ直したいときは、そのボタンを選んで **「Fix this button」** を使います。

## OS ごとの注意

### macOS

キー入力を送るために、許可が必要です：
**システム設定 → プライバシーとセキュリティ → アクセシビリティ** で、アプリを起動したもの
（ターミナル、iTerm、VS Code など）をオンにしてください。オンにしたら、アプリを起動し直します。
これを許可しないと、ボタンは光ってもキーは送られません。

#### Home ボタンで「ゲーム」アプリが開くのを止める

macOS の設定で止めます：**システム設定 → ゲームコントローラ → Home Button → 「Enable Home Button Actions」をオフ**。
アプリ画面の Home ボタン（⚙ 付きラベル）をクリックして「Open Game Controller settings…」からも開けます。

アプリの **Exclusive mode** でも Home を止められますが、その間は Micro が十字キーのデータを送らないため
**十字キーが使えません**。macOS の設定を使ってください。

真ん中の小さい 2 つのボタンは割り当てできません。★ はコントローラーの中で処理され PC に届かず、
Home は電源ボタンを兼ねているためです。

### Windows

追加の設定はいりません。ただし、管理者権限で動いているアプリにキーを送るときは、
このアプリも管理者として起動してください。

## 設定ファイルの場所

| OS | 場所 |
|---|---|
| Windows | `%APPDATA%\8BitDoMicroRemapper\` |
| macOS | `~/Library/Application Support/8BitDoMicroRemapper/` |

`profiles/*.json` にプロファイル、`settings.json` に学習したボタン対応などの設定が保存されます。
プロファイルの形式：

```json
{
  "name": "game",
  "device": "8BitDo Micro",
  "mappings": {
    "a":    {"type": "key", "keys": ["ctrl", "c"]},
    "b":    {"type": "mouse", "button": "right"},
    "home": {"type": "text", "text": "hello"},
    "l2":   {"type": "none"}
  }
}
```

ボタン ID: `up down left right a b x y l r l2 r2 minus plus star home`

## 仕組み

```
8BitDo Micro ──USB──▶ 入力プロセス (pygame-ce / SDL2)
                         │ 押した/離した
                         ▼
                      GUI (tkinter) ── プロファイル ──▶ pynput ──▶ OS へキー/マウス入力
```

macOS では Tk と SDL が同じイベントループを取り合うため、コントローラーの読み取りは別プロセスで行います。

## テスト

```bash
python -m unittest discover -s tests -v
```

## 単体アプリにまとめる（任意）

```bash
pip install pyinstaller
pyinstaller --windowed --name "8BitDo Micro Remapper" run.py
```
