# 双台架异常标样核定

V1 日班流程、数据格式和站库及中心库初始化顺序见 README.md。V2 让次班只凭接纳的两份站件核定共同异常标样。台架的零点各自独立，一个标样在两台架上只有一个实际偏差。

## 核定口径

从所选冻结号读取确切修订，只计该修订的已测行，包括值为零的行。用读数减去固定工单行标称得到标称残差。每行残差等于本站共用零点加本行灵敏度与参考件偏差的内积。配方未引用的参考件在该行的灵敏度为零。偏差和零点均用与读数相同的单位，以有理数精确计算。V2 轮次支持 1～8 个有序参考件，沿用可冻结的非空修订。V1 沿用原范围。

站件须描述全部且仅有这样的公共偏差向量，使本站存在一个零点同时满足所有已测行。单行允许全部偏差向量。本站读数彼此矛盾时，仍可发行表达空关系的站件。逐次读数、逐行残差、行名和逐行配方留在站库。

中心按两份站件的共同坐标核定，先取非零参考件数量最少的共同解释，再取所有这些最少解释的非零参考件交集。必隔离件按参考件在工单上的顺序返回。全零可行返回数量 0 和空清单。无共同解释也定稿，状态为 `impossible`，数量为 `None`，必隔离清单为空。

## Python 接口

沿用 V1 的空闲 SQLite 连接约定。站端沿用原初始化和冻结入口。中心在原初始化后调用 `review.register.initialize_isolation_store(db)`，重复初始化须保留业务历史。

| 入口 | 输入与返回 |
| --- | --- |
| `exchange.issue.issue_isolation_evidence(db, freeze_id)` | 指定站库已存在的冻结号，返回 V2 JSON 正文 `str`。 |
| `exchange.accept.accept_isolation_evidence(db, wire)` | 在中心接纳一份 V2 正文，返回形如 `v2:1` 的字符串接纳号，冒号后为无前导零的正整数。 |
| `review.publish.issue_isolation(db, first_id, second_id)` | 用两份已接纳的 V2 件签发并返回报告字典。接纳号可按任意顺序传入。 |
| `review.readback.read_isolation(db, report_id)` | 按正整数报告号返回原报告字典。读取使用存值，可在站库关闭且中心重开后办理。 |

V2 正文是 JSON 对象，字段为 `version`（整数 2）、`round_id`、`bench_id`、`revision_id`（确切修订的正整数编号）、`bench_order`（工单两台架的有序数组）、`reference_order`（工单参考件的有序数组）和 `relation`。名字沿用 V1 工单规则，序内各自唯一，发行台架须在槽位内。`relation` 使用实现选定并说明的精确表示，须区分全空间与空关系。含有理数值时沿用 V1 的有理数输入规则。接纳校验信封和关系表示，拒绝畸形 JSON、重复键、无效坐标、非法数值及当前表示无法解释的内容。每个接纳号固定首次对应的正文，后续来件不得改写该正文。

两份证据须同轮次、台架不同、工单槽位及参考件的名称和顺序均一致。V2 接口收到 V1 正文或 V1 接纳号、坏件或选件失配时报 `ValueError`。未知冻结号、形状合法但未知的 V2 接纳号或未知报告号报 `KeyError`。超出 V2 参考件范围拒发或拒收，报 `ValueError`。

签发与领取的字典包含 `report_id`、`round_id`、`reference_order`、`status`、`minimum_count`、`required_references`、`sources` 和 `receipt`。状态为 `ok` 时件数是非负整数。参考件顺序与必隔离清单用名字列表。`sources` 是按工单台架槽位排列的两个字典，各含 `acceptance_id`、`bench_id`、`revision_id` 和对应接纳正文 `wire`。`receipt` 含正整数 `receipt_id`、所对应的 `report_id` 和同序列表 `acceptance_ids`。报告、出处和回执同次提交，SQLite 写入失败按 V1 约定抛出异常并整体回滚，故障解除后可用原输入重试。后来勘误、重新签发和中心重开均不改变历史号的结果、回执或来件。

## 样例与验收运行

`check_isolation_inputs.py` 中的 `SAMPLE` 可直接用于原工单和读数入口。`revisions` 按台架与样例名列出各版完整已测行。`cases` 的 `select` 按工单槽位选样例名，`expected` 依次给出状态、最少件数和必隔离清单。`joint` 的两站共同要求 X+Y=1 与 X−Y=0。`tie` 允许单独隔离 X 或 Y。`same_summary` 与 `tie` 在 V1 的两份统计一致，V2 下前者无共同解。运行 `python3 -B check_isolation_inputs.py` 可查看 V1 实际统计并核对原件归属。

交付时沿 `.pointwise-runtime.json` 接通核验和演示。清单保留整数 `version` 1、`kind` 为 `cli`、`setup` 为参数数组的列表、`verify` 和 `demo` 各为一条参数数组。核验保留 `check_project.py` 执行的全部原回归，并校验冻结、闭库反序选件、样例结果及领取。核对失配、混版和签发写失败后的重试，核验失败须以非零状态退出。演示展示实际断源签发的结果，以及源修订勘误并重开中心后按旧号领取的存值和原出处。
