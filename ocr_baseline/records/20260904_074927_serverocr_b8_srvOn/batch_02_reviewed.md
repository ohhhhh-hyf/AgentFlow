# 常见对易恒等式

[A, B] = −[B, A]

[A, B + C] = [A, B] + [A, C]

[A, BC] = [A, B]C + B[A, C]

[AB, C] = A[B, C] + [A, C]B

[A, [B, C]] + [B, [C, A]] + [C, [A, B]] = 0（对称）

[A, B + C] + [B, A + C] + [C, A + B] = 0

## 利用对易关系求解平均值问题

**例1.** 求 $\hat{L}_x$ 和 $\hat{L}_y$ 在 $|l m\rangle$ 下的平均值。

已知 $\hat{L}_z |l m\rangle = m\hbar |l m\rangle$，$[\hat{L}_y, \hat{L}_z] = i\hbar \hat{L}_x$，$[\hat{L}_z, \hat{L}_x] = i\hbar \hat{L}_y$，从而可用含 $\hat{L}_z$ 的表达式表出 $\hat{L}_x$、$\hat{L}_y$。

$$\langle \hat{L}_x \rangle = \langle l m | \hat{L}_x | l m \rangle = \frac{1}{i\hbar} \langle l m | [\hat{L}_y, \hat{L}_z] | l m \rangle = \frac{1}{i\hbar} [\langle l m | \hat{L}_y \hat{L}_z | l m \rangle - \langle l m | \hat{L}_z \hat{L}_y | l m \rangle]$$

由于 $\hat{L}_z |l m\rangle = m\hbar |l m\rangle$，$m$ 为实数，则 $\langle l m | \hat{L}_z = m\hbar \langle l m |$，代入得：

$$\langle \hat{L}_x \rangle = \frac{1}{i\hbar} [m\hbar \langle l m | \hat{L}_y | l m \rangle - m\hbar \langle l m | \hat{L}_y | l m \rangle] = \frac{1}{i\hbar} [m\hbar \langle \hat{L}_y \rangle - m\hbar \langle \hat{L}_y \rangle] = 0$$

同理可得 $\langle \hat{L}_y \rangle = 0$。

**例2.** $|l m\rangle$ 为 $(\hat{L}^2, \hat{L}_z)$ 的共同本征态，求 $\overline{\hat{L}_x^2}$、$\overline{\hat{L}_y^2}$。

$$\overline{\hat{L}^2} = \langle l m | \hat{L}^2 | l m \rangle = l(l+1)\hbar^2 = \langle l m | (\hat{L}_x^2 + \hat{L}_y^2 + \hat{L}_z^2) | l m \rangle = \overline{\hat{L}_x^2} + \overline{\hat{L}_y^2} + m^2\hbar^2$$

利用 $[\hat{L}_x, \hat{L}_y] = i\hbar \hat{L}_z$，即 $\hat{L}_x \hat{L}_y - \hat{L}_y \hat{L}_x = i\hbar \hat{L}_z$，可得：

$$\hat{L}_x \hat{L}_y = \hat{L}_y \hat{L}_x + i\hbar \hat{L}_z$$

$$\hat{L}_x^2 - \hat{L}_y^2 = (\hat{L}_x - \hat{L}_y)(\hat{L}_x + \hat{L}_y) = [\hat{L}_x, \hat{L}_y] + \hat{L}_y \hat{L}_x - \hat{L}_x \hat{L}_y - \hat{L}_y^2 + \hat{L}_x^2$$

整理得：

$$\overline{\hat{L}_x^2} = \frac{1}{2} [l(l+1) - m^2]\hbar^2 + \frac{1}{2} \langle l m | (\hat{L}_x^2 - \hat{L}_y^2) | l m \rangle$$

由对称性 $\langle \hat{L}_x^2 \rangle = \langle \hat{L}_y^2 \rangle$，故：

$$\overline{\hat{L}_x^2} = \overline{\hat{L}_y^2} = \frac{1}{2} [l(l+1) - m^2]\hbar^2$$

**方法总结：** 将本征态对应的算符尽量转化到最左/右边，直接作用到态矢上。

# 不确定度关系的严格证明

任意给定力学量 $A$ 和 $B$，对应的厄米算符为 $\hat{A}$ 和 $\hat{B}$，分别具有不确定度 $\Delta A$ 和 $\Delta B$，则有以下关系：

$$\Delta A \Delta B \ge \frac{1}{2} |\langle [\hat{A}, \hat{B}] \rangle|$$

其中 $\langle [\hat{A}, \hat{B}] \rangle = \langle \Psi | [\hat{A}, \hat{B}] | \Psi \rangle$ 对 $|\Psi\rangle$ 成立，$\Delta A = \hat{A} - \bar{A}$，$\Delta B = \hat{B} - \bar{B}$。

$$[\hat{A}, \hat{B}] = [\Delta A + \bar{A}, \Delta B + \bar{B}] = (\Delta A + \bar{A})(\Delta B + \bar{B}) - (\Delta B + \bar{B})(\Delta A + \bar{A}) = [\Delta A, \Delta B]$$

$$\Delta A = \sqrt{\langle \hat{A}^2 \rangle - \langle \hat{A} \rangle^2} = \sqrt{\langle (\hat{A} - \bar{A})^2 \rangle}, \quad \Delta B = \sqrt{\langle (\hat{B} - \bar{B})^2 \rangle}$$

要证也即 $\langle (\hat{A} - \bar{A})^2 \rangle \cdot \langle (\hat{B} - \bar{B})^2 \rangle \ge \frac{1}{4} |\langle [\hat{A} - \bar{A}, \hat{B} - \bar{B}] \rangle|^2$。

令 $\hat{x} = \hat{A} - \bar{A}$，$\hat{y} = \hat{B} - \bar{B}$，要证变为：$\langle \hat{x}^2 \rangle \cdot \langle \hat{y}^2 \rangle \ge \frac{1}{4} |\langle [\hat{x}, \hat{y}] \rangle|^2$。联想 $b^2 \ge 4ac$。

考虑 $|\phi\rangle = \xi \hat{x} |\Psi\rangle + i \hat{y} |\Psi\rangle$，$\langle \phi | \phi \rangle \ge 0$：

$$\langle \xi \hat{x} |\Psi\rangle + i \hat{y} |\Psi\rangle | \xi \hat{x} |\Psi\rangle + i \hat{y} |\Psi\rangle \rangle = (\xi \langle \Psi | \hat{x} + (-i) \langle \Psi | \hat{y})(\xi \hat{x} |\Psi\rangle + i \hat{y} |\Psi\rangle)$$

$\hat{x}, \hat{y}$ 为厄米算符（$\because \langle \Psi | \hat{x} - i \langle \Psi | \hat{y})(\xi \hat{x} |\Psi\rangle + i \hat{y} |\Psi\rangle)$）

$$= (\xi \langle \Psi | \hat{x}^\dagger - i \langle \Psi | \hat{y}^\dagger)(\xi \hat{x} |\Psi\rangle + i \hat{y} |\Psi\rangle)$$

$$= \xi^2 \langle \Psi | \hat{x}^2 | \Psi \rangle + \langle \Psi | \hat{y}^2 | \Psi \rangle + i\xi (\langle \Psi | \hat{x} \hat{y} | \Psi \rangle - \langle \Psi | \hat{y} \hat{x} | \Psi \rangle) = \xi^2 \langle \hat{x}^2 \rangle + \langle \hat{y}^2 \rangle + i\xi \langle [\hat{x}, \hat{y}] \rangle$$

由 $\langle \phi | \phi \rangle \ge 0$，$(i\langle [\hat{x}, \hat{y}] \rangle)^2 \le 4 \langle \hat{x}^2 \rangle \langle \hat{y}^2 \rangle$，即 $\langle \hat{x}^2 \rangle \cdot \langle \hat{y}^2 \rangle \ge \frac{1}{4} |\langle [\hat{x}, \hat{y}] \rangle|^2$。

$$\therefore \Delta A \Delta B \ge \frac{1}{2} |\langle [\hat{A}, \hat{B}] \rangle|$$

**对任意力学量 $A, B$ 和任意量子态 $|\Psi\rangle$，若 $A$ 与 $B$ 不对易即 $[\hat{A}, \hat{B}] \neq 0$，则 $\Delta A$ 和 $\Delta B$ 不能同时为零，也即 $A$ 与 $B$ 不能同时测定。**

## 共同本征函数

设 $\hat{A} \psi_A = A \psi_A$，$\hat{B} \psi_B = B \psi_B$。若 $[\hat{A}, \hat{B}] \neq 0$，则 $\psi_A$ 不是 $\hat{B}$ 的本征函数，$\psi_B$ 不是 $\hat{A}$ 的本征函数。

若 $[\hat{A}, \hat{B}] = 0$，则可能存在 $\psi$，使 $\hat{A} \psi = A \psi$，$\hat{B} \psi = B \psi$。此时称 $\psi$ 为 $A$ 和 $B$ 的共同本征函数。

**定理：** 设 $\hat{A} |k\rangle = a_k |k\rangle$，另有 $\hat{B}$，若 $[\hat{A}, \hat{B}] = 0$，且 $a_k$ 不简并（即 $a_k$ 只对应一个本征态 $|k\rangle$），则 $|k\rangle$ 也是 $\hat{B}$ 的本征态，即 $A$ 和 $B$ 拥有共同本征态。

**证明：** $[\hat{A}, \hat{B}] = 0 \Rightarrow \hat{A}\hat{B} = \hat{B}\hat{A}$。$\hat{B}\hat{A}|k\rangle = \hat{B} \cdot a_k |k\rangle = a_k \hat{B}|k\rangle$。则 $\hat{A}(\hat{B}|k\rangle) = a_k (\hat{B}|k\rangle)$，故 $\hat{B}|k\rangle$ 也是 $\hat{A}$ 属于本征值 $a_k$ 的本征态。故 $\hat{B}|k\rangle$ 与 $|k\rangle$ 是同一个量子态，即 $\hat{B}|k\rangle = b_k |k\rangle$。$\Rightarrow A, B$ 拥有共同本征态 $|k\rangle$。

**例：** $\psi_{\vec{p}}(\vec{r}) = \frac{1}{(2\pi\hbar)^{3/2}} e^{i\vec{p} \cdot \vec{r}/\hbar}$ 为 $\hat{p}_x, \hat{p}_y, \hat{p}_z$ 的共同本征函数，本征值为 $p_x, p_y, p_z$。$\hat{p} \psi_{\vec{p}}(\vec{r}) = \frac{\hbar}{i} \nabla \psi_{\vec{p}}(\vec{r}) = \vec{p} \psi_{\vec{p}}(\vec{r})$。

# 厄米算符本征值与本征态的特性

## 转置算符、共轭算符与厄米算符

**转置算符**：对 $V$ 和 $Y$，若 $\langle \phi|A|\psi\rangle = \langle \psi|A^T|\phi\rangle$，则称 $A$ 和 $A^T$ 互为彼此的转置算符。

**共轭算符**：对算符 $A$ 的每一项取复共轭，得到 $A^*$ 为 $A$ 的转置算符。

**厄米算符**：$A = A^\dagger = A^*$，则称 $A$ 为厄米算符。

## 厄米算符平均值为实数

**定理**：厄米算符 $A$ 在任意量子态下的平均值 $\bar{A}$ 为实数，$A^2$ 的平均值 $\overline{A^2} \ge 0$。

$$\langle \phi|A|\phi\rangle = \langle \phi|A^\dagger|\phi\rangle = \langle \phi|A^*|\phi\rangle = \langle \phi^*|A|\phi^*\rangle = (\langle \phi|A|\phi\rangle)^*$$

因为 $A = A^\dagger = A^*$，所以 $A$ 为实数。

或：$\langle \phi|A^\dagger|\phi\rangle = \langle A\phi|\phi\rangle$，$\langle \phi|A|\phi\rangle = \langle A\phi|\phi\rangle$，$A = A^\dagger = A^*$，$A$ 为实数。

$$|\phi\rangle = A|\phi\rangle$$

$$\langle \phi|A^2|\phi\rangle = \langle \phi|AA|\phi\rangle = \langle \phi|A^\dagger A|\phi\rangle = \langle A\phi|A\phi\rangle = \langle \phi|\phi\rangle \ge 0, \quad A \ge 0$$

## 厄米算符本征值的实数性

$$F|k\rangle = \lambda_k |k\rangle$$

则 $\langle k|F|k\rangle = \bar{F} = \langle k|\lambda_k |k\rangle = \lambda_k \langle k|k\rangle = \lambda_k$，因为 $\lambda_k = \bar{F}$ 为实数。

## 厄米算符本征态的正交性与完备性、封闭性

### 正交性

① 厄米算符属于不同本征值的本征态必然正交（对不同 $|k\rangle$ 可能有不同的 $\lambda_k$）。

$$F|k\rangle = \lambda_k |k\rangle, \quad F|k'\rangle = \lambda_{k'} |k'\rangle$$

$$\langle k'|F|k\rangle = \lambda_k \langle k'|k\rangle, \quad \langle k'|F|k\rangle = \langle k'|F^\dagger|k\rangle = \langle Fk'|k\rangle = \lambda_{k'} \langle k'|k\rangle$$

又 $\lambda_k$ 为实数，$\lambda_k = \lambda_k^*$，$\langle k'|F|k\rangle = \lambda_k \langle k'|k\rangle = \lambda_{k'} \langle k'|k\rangle$，而 $\lambda_k \ne \lambda_{k'}$，故 $\langle k'|k\rangle = 0$，即 $|k'\rangle$ 与 $|k\rangle$ 正交。

### 完备性

② 本征态的完备性

$P = |k\rangle\langle k|$ 为投影算符，$P = \sum_k P_k$。

若对 $\forall |\phi\rangle$，有 $P|\phi\rangle = \sum_k |k\rangle\langle k|\phi\rangle = |\phi\rangle$，则称基矢 $|k\rangle$ 具有完备性。（任意 $|\phi\rangle$ 可按 $|k\rangle$ 展开）

记 $C_k = \langle k|\phi\rangle$，则 $|\phi\rangle = \sum_k |k\rangle\langle k|\phi\rangle = \sum_k C_k |k\rangle$，$C_k$ 为用 $|k\rangle$ 将 $|\phi\rangle$ 做展开时的展开系数。

**定理**：哈密顿算符 $H$ 为厄米算符，满足本征方程 $H|k\rangle = E_k |k\rangle$，对体系的任一归一化态 $|\phi\rangle$，若 $\bar{H} = \langle \phi|H|\phi\rangle$ 有下界（总大于某常数）但无上界，则 $H$ 的本征态 $|k\rangle$ 的集合构成体系的一个**完备集**，即体系的任一量子态 $|\phi\rangle$ 可用 $|k\rangle$ 来展开。

0,x<0
>An=√/z[a-Seka+tsin2(kna)]*
√n(X)=<Ansin(knx),O<x<a
Bn=z[a-zknsin(2kna)+tnsin(kna)]+.eaposinkna
# 一个En对应一个／n
一维谐振子
(-Kx=mx,x+ax=0,w2=m)
V(x)=2±2Kx2=/±Mw2x2
薛定谔方程：[﹣聶器＋/mw2x2]4(0)=E4(x)
令α=x,§=αx，入＝磊．记4(x)=(4(§(x0)=(5)．于是，-x2(4(3)=-(4().
帶﹣端5(4(3)＝一π(4(3),)-52(4(s)＝一入4(3),2+（入﹣5)4(3)=0
为"消除"32项，试探设4(3)=e-2H(3)=>A)-23+（入﹣1)H(S)=0.
4(8)0．仅当入＝2n+1时，Hn(3）有4(3)∞O解，H(S)=Ha(3)=(-1)"e3器e".(?)
H(s)H.(3)es ds=n2".n! 8nn(?)
4n(s)=Nne-2Ha(3),NaeHa(S)H,(s)dx=(x)4,(x)dx=1,Nn=／反·[/T·2°-n!]+()·/zm
能量分立化 En＝孕hw=(n+z)tcw4n(x)=N.e-Ha(ax)
补充（方程）-23+（入﹣1)H(S)=O的两种解法）
①幂级数解法，构造递推的系数关系
H(S)＝盖Q;8,zli(i-n)a;si2-2jajsi+（入﹣)a;S']=O=>(j+2)(j+1)aj+2-(2j+1﹣入）aj=0
i、aj+2=aj，若级数解存在无穷多项，aj喻，H(s)~2(5)*=ce
>(4(3）按e量级增长，不可积＝＞级数存在（只有）有限项＝→3an≠0,an+2=0，即入＝2n+1.
从而有aj22＝品aj，多项式H(S）只能含奇数项或偶数项，系数由高次项推至低次项
方程可变化为）-25+2nH(s)=O，其解为厄米多项式Hn(3).
HuS)=(2s)k=(-1)"e(e-s)（可通过递推＋母函数求解）
Hn(s）满足：Hnti(3)-2SHn(s)+2NHm(3)=O 母函数W(t,x)=ex+x-++2(t-x)4(t,x)=0
华中科技大学附属印刷厂 W(t,x)=【Ha(x)．箭第

③本征态的封闭性

称为投影算符成的封闭性．

# 本征态的封闭性

$\hat{I}$ 为单位算符，$\forall |\psi\rangle$，$\hat{I}|\psi\rangle = |\psi\rangle$。

若本征态或基矢 $|k\rangle$ 满足 $\sum_k |k\rangle\langle k| = \hat{I}$，称为本征态或基矢 $|k\rangle$ 的封闭性；$\sum_k \hat{P}_k = \sum_k |k\rangle\langle k| = \hat{I}$，称为投影算符 $\hat{P}_k$ 的封闭性。

**完备性与封闭性**：强调重点不同，完备性指任意 $|\psi\rangle$ 可按 $\{|k\rangle\}$ 展开，封闭性指数学上封闭性方程 $\sum_k |k\rangle\langle k| = \hat{I}$ 成立，两者相互依存。

**例**：设体系的能量本征方程为 $\hat{H}|k\rangle = E_k|k\rangle$，证明哈密顿算符可表示为 $\hat{H} = \sum_k E_k |k\rangle\langle k|$（本征态具有完备性、封闭性）。

定理若 [F,H]=0，[G,H]=0，但 [F,G]≠0，则体系的能级是简并的。（F、G 为守恒量）

又 GF₄ = FG₄ ≠ FG₄，则 G₄ 不是 F 的本征态，G₄ 和 F₄ 不是一个态，即 E 对应至少两个态，能级简并。

$\hat{H}\sum_k |k\rangle\langle k| = \sum_k E_k |k\rangle\langle k|$，则 $\hat{H}\sum_k |k\rangle\langle k| = \hat{H}\hat{I} = \hat{H} = \sum_k E_k |k\rangle\langle k|$，从而有 $\hat{H}\hat{I} = \hat{H} = \sum_k E_k |k\rangle\langle k|$。

# 守恒量与能级简并度

## 力学量平均值的时间依赖特性

$\bar{A}(t) = \langle \psi(t) | \hat{A} | \psi(t) \rangle$。薛定谔方程：$i\hbar \frac{\partial}{\partial t}|\psi(t)\rangle = \hat{H}|\psi\rangle$。在左矢空间中：$-i\hbar \frac{\partial}{\partial t}\langle\psi| = \langle\psi|\hat{H}$（$\hat{H}^\dagger = \hat{H}$）。

$\frac{d\bar{A}}{dt} = \frac{\partial}{\partial t}\left(\langle\psi|\hat{A}|\psi\rangle\right) = \left\langle\frac{\partial\psi}{\partial t}\Big|\hat{A}\Big|\psi\right\rangle + \left\langle\psi\Big|\frac{\partial\hat{A}}{\partial t}\Big|\psi\right\rangle + \left\langle\psi\Big|\hat{A}\Big|\frac{\partial\psi}{\partial t}\right\rangle = \frac{1}{i\hbar}\langle\psi|\hat{A}\hat{H}|\psi\rangle + \left\langle\psi\Big|\frac{\partial\hat{A}}{\partial t}\Big|\psi\right\rangle + \frac{1}{i\hbar}\langle\psi|\hat{H}\hat{A}|\psi\rangle$

$\frac{d\bar{A}}{dt} = \frac{1}{i\hbar}\langle\psi|[\hat{A},\hat{H}]|\psi\rangle + \left\langle\psi\Big|\frac{\partial\hat{A}}{\partial t}\Big|\psi\right\rangle$，若 $\frac{\partial\hat{A}}{\partial t} = 0$（$\hat{A}$ 不显含 $t$）且 $[\hat{A},\hat{H}] = 0$，则 $\frac{d\bar{A}}{dt} = 0$，$\bar{A}$ 与时间无关。

$\hat{A}$ 在任何态 $\psi(t)$ 下的平均值 $\bar{A}$ 都不随时间改变。

## 守恒量

$\hat{A}$ 在任何态 $\psi(t)$ 下的平均值 $\bar{A}$ 都不随 $t$ 改变，则称此时 $\hat{A}$ 对应的力学量为体系的一个**守恒量**。

$\frac{\partial\hat{A}}{\partial t} = 0$ 且 $[\hat{A},\hat{H}] = 0 \Rightarrow \hat{A}$ 为守恒量。

**定理**：若 $[\hat{F},\hat{H}] = 0$，$[\hat{G},\hat{H}] = 0$，但 $[\hat{F},\hat{G}] \neq 0$，则体系的能级是简并的。（$\hat{F}$、$\hat{G}$ 为守恒量）

$\hat{F}$、$\hat{H}$ 有共同本征函数 $\psi$：$\hat{F}\psi = F\psi$，$\hat{H}\psi = E\psi$。$[\hat{G},\hat{H}] = 0$，则 $\hat{H}(\hat{G}\psi) = \hat{G}\hat{H}\psi = \hat{G}(E\psi) = E(\hat{G}\psi)$。

又 $\hat{F}(\hat{G}\psi) = \hat{F}\hat{G}\psi \neq \hat{G}\hat{F}\psi = FG\psi$，则 $\hat{G}\psi$ 不是 $\hat{F}$ 的本征态，$\hat{G}\psi$ 和 $\psi$ 不是一个态，即 $E$ 对应至少两个态，**能级简并**。

# 表象变换与矩阵力学

设 $F=(A_1, A_2, \ldots, A_n)$ 是一组力学量完全集，$|k\rangle$ 是共同本征态，其中 $k$ 表征所有量子数。$|k\rangle$ 是正交归一的，满足 $\langle k | m \rangle = \delta_{km} = \begin{cases} 1, & k = m \\ 0, & k \neq m \end{cases}$，$|k\rangle$ 是完备的，即体系中任一量子态可按 $|k\rangle$ 展开。

$|k\rangle$ 构成一个表象，可称为 $F$ 表象，$F$ 构成无穷维的希尔伯特空间。量子态 $|\psi\rangle$ 是希尔伯特空间中的一个矢量：$|\psi\rangle = \sum_k a_k |k\rangle$，则 $a_k = \langle k | \psi \rangle$ 为内积，也可视为"投影"。

## 表象间的转化

$F$ 表象中，$|k\rangle$ 为基矢，$|\psi\rangle = \sum_k a_k |k\rangle$，$|\psi\rangle$ 在 $F$ 表象中可用系数列向量表示为 $a = \begin{pmatrix} a_1 \\ a_2 \\ \vdots \end{pmatrix}$。

另一 $F'$ 表象中，$|\beta\rangle$ 为基矢，$|\psi\rangle = \sum_\beta a_\beta' |\beta\rangle$，在 $F'$ 表象中可表示为 $a' = \begin{pmatrix} a_1' \\ a_2' \\ \vdots \end{pmatrix}$。

$a'$ 与 $a$ 的转化实际上是基矢之间的转化。

$|\psi\rangle = \sum_k a_k |k\rangle = \sum_\beta b_\beta |\beta\rangle$，$|k\rangle = \sum_\beta \langle \beta | k \rangle \cdot |\beta\rangle$（$|k\rangle$ 按 $|\beta\rangle$ 展开），从而统一基矢为 $|\beta\rangle$。

记 $S_{\beta k} = \langle \beta | k \rangle$，$S = (S_{\beta k})$，则 $a_\beta' = \sum_k a_k \cdot \langle \beta | k \rangle$，$a' = S a$，即 $a' = S a$，$S^\dagger S = S S^\dagger = 1$。

**注**：$a$、$a'$ 均为系数列向量，与本征态形式相似但意义完全不同。$|k\rangle$ 在希尔伯特空间中可表示为一个列向量，$|\psi\rangle$ 按 $|k\rangle$ 展开所得系数列为 $a$。

$a = \begin{pmatrix} a_1 \\ a_2 \\ \vdots \end{pmatrix} = \begin{pmatrix} \langle e_1 | \psi \rangle \\ \langle e_2 | \psi \rangle \\ \vdots \end{pmatrix}$

从矢量的角度考虑，$|\psi\rangle = \begin{pmatrix} e_1 & e_2 & \cdots \end{pmatrix} \begin{pmatrix} a_1 \\ a_2 \\ \vdots \end{pmatrix}$，即列向量 $e_i'$ 的线性组合系数列。

要"消去" $(e_1', e_2', \ldots, e_n')$，则 $\begin{pmatrix} e_1 & e_2 & \cdots & e_n \end{pmatrix} = \begin{pmatrix} e_1' & e_2' & \cdots & e_n' \end{pmatrix} \begin{pmatrix} S_{11} & S_{12} & \cdots & S_{1k} & \cdots \\ S_{21} & S_{22} & \cdots & S_{2k} & \cdots \\ \vdots & \vdots & & \vdots & \\ S_{k1} & S_{k2} & \cdots & S_{kk} & \cdots \end{pmatrix}$

$\langle k' | k \rangle = \delta_{k'k}$，$\langle k | k \rangle = 1$，$|k\rangle = \sum_\beta S_{\beta k} |\beta\rangle$，$\langle k | k \rangle = \left( \sum_\beta S_{\beta k}^* \langle \beta | \right) \left( \sum_\beta S_{\beta k} |\beta\rangle \right) = \sum_\beta |S_{\beta k}|^2 = 1$

$\langle m | k \rangle = \left( \sum_\beta S_{\beta m}^* \langle \beta | \right) \left( \sum_\beta S_{\beta k} |\beta\rangle \right) = \sum_\beta S_{\beta m}^* S_{\beta k} = \delta_{mk}$

即 $S^\dagger S = I$，**$S$ 为幺正矩阵**。

$\begin{pmatrix} \langle e_1 | e_1 \rangle & \langle e_1 | e_2 \rangle & \cdots \\ \langle e_2 | e_1 \rangle & \langle e_2 | e_2 \rangle & \cdots \\ \vdots & \vdots & \ddots \end{pmatrix} = \begin{pmatrix} e_1 & e_2 & \cdots \end{pmatrix}^\dagger \begin{pmatrix} e_1 & e_2 & \cdots \end{pmatrix} = \begin{pmatrix} \langle e_1' | e_1' \rangle & \langle e_1' | e_2' \rangle & \cdots \\ \langle e_2' | e_1' \rangle & \langle e_2' | e_2' \rangle & \cdots \\ \vdots & \vdots & \ddots \end{pmatrix} S = I S = S$

中心力场
疟＝-DV(2),V(7)=V(r)，称为中心力场
√2在坐标表象下为＋+，采用球坐标表示为▽2=(P剂）+F2sng晶（smo品）+rishre和
又个＝一片［s弱（smo录）+s瓶制，于是A4＝一范产乔（r剂4+[3+v(r)]4=E4
采用分离变量法，令4(r,0,4)=R(r)Y(0,4)，则一最广奇（r警）Y(0,4)+(V(N)-E)R(r)Y(0,p)-
(sho (sinoY).Rir)+smR(r)]=0
一（)+(V(r-E)=·[(sing)+]
1明（2)+2F[E-V(N]=-[so(sin)+]＝入．
经向方程：[rr&P]+［等（E-v(r)-]R(r)=O
角向方程：5(sine)+＝一入Y(,4)，即℃2Y(0,4)＝入た2Y10,4)
①考虑角向方程．Y(8,4)=④(0）中（4)
se o[sined中（4)+s④(o)＝一入（0)(4)=＞晶［sine]+＋入sin=0
>[sime]＋入sin2e=-)=m2
sinea[singd]+(a-3)④(8)=0…勒让德方程
(2+m2（中（4)=0=→中m(p)==eimv
对于勒让德方程smedh[sine]+（入﹣s)④(0)=0，为使④(0）在区间［0,π］有限，入只能取
(((+1),(=0,1,2,…(l为轨道量子数）H(0)=④Lm(8)=P.lm(casB)=Bim(1-cos2o)aPi(cosO)
|m]≤l时才有④(⊙)≠O=)m=0,±1,..,±l.
。(o)④(o)sino do=Sei,Bim=
-m(2+,Yim(0,P)=⑨cm(8)Pm(4)=Num(1-cos20)2(a(ooPr(coso)]eimb
Nim=2，球谐函数满足正交关系：。。Yu(0.4)Ycm(0,4)sinodod4=Sr'lSm'm
4π(Hm).
(2Yum=l(l+1）片2Yum,122Yum=r2m2Yum=>Yum是C2.2的共同本征态

zhnh华中科技大学
hut
氢原子
径向方程：（器）+［等（E-V(n)-]R=0
v(r)=-,ki=．则方程为外（2)+［装（E+)-]R(r)=0
引入约化径向波函数u(r)=rRi(r)，则u(r）满足部＋［装（E＋华）-]u(r)=0.
:v(r)<0,Ri(r)50∞,0,r→0∞时薛定谔方程约为＋U(n)=0，若E>o,u(r）呈振荡形式，
不满足束缚态，则E<O．从能量角度分析，E=V+K,k<|vl,E<0.
核与电子"双星模型"
M为约化质量，M=/e．定义无量纲变量p=ar,α=,B=
于是方程化为：+[-+-(]u(p)=0
p→00时，方程近似为一本（u(p)=0.u(p)~e-s( p-0)
9→0时，方程近似为是﹣(+2)u(p)=0.u(p)~p(+
利用渐进解，设u(p)=p+e-f v(p).
V(P）满足方程P敬＋(2l+2-P）部＋(B-(l+1)]V(P)=0，为合流超几何方程
v(e）有多项式解的条件是B-(-1=nr,B=l+1+nr(nr=0,1,…)．令n=l+|+nr,n=1,2,…
>En=﹣市
B==n,:E,=﹣市仅与n相关
l的取值为0,1,…,n-1;m的取值为一l,-(1-1),…0.1,…l．能量本征态由（n,l,m）表征
氢离子轨道角动量的取值L2＝入だ=(l+1)(ち2 C2Y＝入片Y
氢离子轨道角动量2方向的取值：Lz=m方CzY=mtY
归一化条件：SIUmt(r)l2dr=。1Rai(1)12r2dr-1 SSo4mm (r,0,4)4num(r, 0,4) r2sino drdode=Snndi dor
能级简并 n=nr+l+1，能级简并度fn＝器。(2(+1)=n2
径向位置概率分布（r,r+dr）内概率为r2dr Jf14mlm(r, 0,4)12 sino do d4= r2|Rmc(t)I2 dr=(Unu(r)l2dr
Unl(r）的节点数为nr=n-1-1. nr=0的态称为圆轨道，Mnm(r)12极大值位置为rn=n2ao,Qa=e
:6944192702325

GUNIVERSITY OF SCIENCEANDT
OF SCIENCE AND TECHNOLOGY
R.China 中国．武汉 T

HH华中科技大学
NGUNIVERSITY OF SCIENCE ANDI
④常见对易恒等式

A.B为厄米算符（乡＜41A-i<41B)(§A14>+iB14>)

真＝[mt<(m|G|(m>-<|m|G|(m>]．六及＝瓦＝0

列向量e:'的线性组
Ssi S22…Sok…
Sp+S2-Sk…)

S为么正矩阵
(ei,ei)(t.e)(ei.ep)…

A在任何态4(t）下的平均值A都不随时间改变

例1．求以和ly在1(m＞下的平均值．