"""测试公共支撑代码（pytest 不收集本目录）。

- ``expectations``：会抛 ``AssertionError`` 的断言助手，替代静默 ``check()``；
- ``builders``：测试数据构造器，供 Step 5/6 逐步抽取复用；
- ``fakes``：轻量替身，供 Step 5/6 收敛各测试文件里的局部实现。
"""
