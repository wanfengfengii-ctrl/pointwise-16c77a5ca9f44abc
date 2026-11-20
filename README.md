# 双台架校准交班台账 V1

精密量具厂的校准室每班用标样的差值读数检查两座台架的零点和重复测量离散。日班允许勘误以及证据重投，交班后两座站库可以关闭。次班按正式号领取当时采用的两份诊断，决定优先复测哪座台架。

## 运行

在项目根目录使用 Python 3.11 和标准库 SQLite。交付环境提供原回归入口，演示在每次运行时建立独立临时库。

```sh
python3 -B check_project.py
python3 -B demo.py
```

## 一天的工作

1. 规程员根据标样证书及工单，在两座站库登记同一轮次。工单固定有序参考件、两座台架及各自具名的带符号配方。
2. 操作员用行名提交本台架读数。系统按配方行序保存已测位置并返回修订号，先提交的行可以位于配方末尾。
3. 操作员以确切父修订提交更正后的完整读数集。校准员可以选择原修订或新修订冻结。
4. 校准员按冻结号定稿本机零点、有效行数、逐行偏差和残差平方和，取得站内报告号。
5. 证据员按报告号发行摘要。中心接纳并固定首份正文，等价重投沿用原接纳号。接纳后关闭两个站库。
6. 中心拿两个明确的接纳号签发。正式报告把各台架统计量和对应首纳号按工单槽位排列，同次提交回执。
7. 次班重开中心，按正式号领取存值、回执和两份原来件。后来勘误可以另发报告，两个编号分别查询。

## 计算及数据口径

读数、标称、零点和逐行偏差以微米计，灵敏度无量纲，残差平方和以平方微米计。每行先用配方对同轮参考件的标称值作带符号加权求和，再用读数减行标称值得到标称残差。有效行标称残差的算术平均是本机零点。逐行偏差为标称残差减本机零点，平方和以这些偏差计算。缺席行没有统计贡献。单行的逐行偏差与平方和都为零。

录入支持整数、`Fraction` 和有理文本，例如 `-3`、`0.50`、`-2/4`。允许文本首尾空白，整数分数须有非零整数分母。布尔、浮点、空值和坏数值报 `ValueError`。有理零是有效读数。样例的 B 台配方 a 为 X−Y、b 为 X，X 和 Y 分别为 2 和 3。反序录入 b=2、a=0 后，标称残差按行序为 1、0，零点为 1/2，逐行偏差为 1/2、−1/2，平方和为 1/2。勘误 a=2 后，B 台新零点和平方和分别为 3/2、9/2。A 台只测 a，零点为 4，平方和为 0。演示实际签发并核对 B、A 槽位及重开后的旧号和新号。

## Python 接口

接口接收同一库的一条 `sqlite3.Connection`。请使用空闲连接调用初始化及业务写入接口，由接口持有事务边界。站库按序调用 `protocol.rounds.initialize_round_store`、`intake.revisions.initialize_revision_store`、`intake.freeze.initialize_freeze_store`、`fit.local_reports.initialize_local_report_store`。中心库按序调用 `exchange.catalog.initialize_acceptance_store` 和 `review.register.initialize_comparison_store`。重复初始化保留已有记录和用户提交的更正。一座发行台架沿用自己的站库和报告编号空间。

| 模块 | 入口及结果 |
| --- | --- |
| `protocol.rounds` | `register_round(db, round_id, references, benches)` 返回 `RoundPlan`，`get_round(db, round_id)` 读取固定快照。`RoundPlan.bench(bench_id)` 返回配方和有序标称。 |
| `intake.measurements` | `record_readings(db, round_id, bench_id, readings, corrects=None)` 返回新修订号。`corrects` 为仅限关键字的父修订号。 |
| `intake.revisions`、`intake.freeze` | `get_revision(db, revision_id)` 读取修订，`freeze_revision(db, revision_id)` 返回冻结号，`get_frozen_revision(db, freeze_id)` 读取冻结及确切修订。 |
| `fit.local_reports` | `issue_local(db, freeze_id)` 定稿并返回含编号的 `LocalReport`，`get_local_report(db, report_id)` 读取存值。 |
| `exchange.issue`、`exchange.accept`、`exchange.catalog` | `issue_summary(db, local_report_id)` 返回 V1 JSON 文本，`accept_summary(db, wire)` 返回首纳号，`get_accepted_summary(db, acceptance_id)` 返回解析件和首纳原文。 |
| `review.publish`、`review.readback` | `issue_comparison(db, first_id, second_id)` 返回含回执的 `ComparisonReport`，`read_comparison(db, report_id)` 返回该报告和两份首纳件。 |

工单和读数使用有序的列表或元组对。`references` 的条目是 `(参考件名, 标称值)`，`benches` 的条目是 `(台架名, 行列表)`，每行形如 `(行名, [(参考件名, 灵敏度), ...])`。工单至少有一个参考件，恰有两座异名台架，每座至少一行，每行至少一项，行内参考件唯一。`readings` 的条目是 `(行名, 读数)`，同一修订每行至多出现一次。空读数集可以保存为待补全修订。更正时提交该版希望保留的全部已测行。

V1 摘要固定八个字段。`version` 是整数 `1`，`round_id`、`bench_id`、`local_report_id`、`bench_order` 表示来源和工单顺序，`zero_point`、`row_count`、`residual_ss` 表示本地统计。发行把有理统计写为约分文本。接纳按解析后的完整值比较，允许字段重排和等值分数字符串，拒绝缺字段、额外字段和重复 JSON 键。逐次读数、配方及本地明细留站。

重复工单、未知配方引用、行或台架失配、跨轮或跨台架勘误、空修订冻结、坏件、来件冲突及选件失配报 `ValueError`。未知轮次、被勘误修订、冻结、本地报告、接纳号和正式号报 `KeyError`。写入失败向调用方传播 SQLite 异常并回滚该次业务写入，故障解除后可用原输入重试。目录、报告和修订接口以追加写入保存业务历史。
