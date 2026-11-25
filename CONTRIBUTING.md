# 参与贡献

本地知识库检索问答：BM25 检索、模型带引用作答、引用逐条回原文核对。

## 本地跑起来

```bash
git clone https://github.com/wushiyi105-jpg/zhiku.git
cd zhiku
cp .env.example .env      # Windows: copy .env.example .env
# 打开 .env，把 LLM_API_KEY 换成你自己的

python -m zhiku add samples/员工手册.md samples/云盘产品答疑.md
python -m zhiku ask "报销最晚多少天内必须提交？超过会怎样？"
python -m zhiku serve     # http://127.0.0.1:8765
```

## 跑测试

```bash
python -m unittest discover tests -v
```

单测不依赖真 key：所有模型调用在测试里都换成了假客户端，没配 .env 也能全绿。Windows 终端如果中文乱码，先把环境变量 PYTHONIOENCODING 设成 utf-8。

## 提 PR

1. fork 本仓库，从 main 开一个分支，名字说清要干什么，比如 fix-csv-encoding。
2. 改代码，能顺手补一个测试就补。
3. 本地把上面的测试命令跑一遍，全绿再往下走。
4. 提 PR，写三件事：改了什么、为什么改、本地测试结果。
5. 动到模型调用那一层的，贴一段真实运行输出，比任何描述都省事。

不用写得很正式，说清楚就行。
