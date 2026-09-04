# 常见对易恒等式

- $[A, B] = -[B, A]$
- $[A, B+C] = [A, B] + [A, C]$
- $[A, BC] = [A, B]C + B[A, C]$
- $[AB, C] = A[B, C] + [A, C]B$
- $[A, [B, C]] + [B, [C, A]] + [C, [A, B]] = 0$（Jacobi 恒等式）
- $[A, B+C] + [B, A+C] + [C, A+B] = 0$

## 利用对易关系求解平均值问题

**例1．** 求 $\hat{L}_x$ 和 $\hat{L}_y$ 在 $|l m\rangle$ 下的平均值。

已知 $\hat{L}_z |l m\rangle = m\hbar |l m\rangle$，$[\hat{L}_y, \hat{L}_z] = i\hbar \hat{L}_x$，$[\hat{L}_z, \hat{L}_x] = i\hbar \hat{L}_y$，从而可用含 $\hat{L}_y$ 的表达式表出 $\hat{L}_x$。

$\langle \hat{L}_x \rangle = \langle l m | \hat{L}_x | l m \rangle = \frac{1}{i\hbar} \langle l m | [\hat{L}_y, \hat{L}_z] | l m \rangle = \frac{1}{i\hbar} [\langle l m | \hat{L}_y \hat{L}_z | l m \rangle - \langle l m | \hat{L}_z \hat{L}_y | l m \rangle]$

由于 $\hat{L}_z | l m \rangle = m\hbar | l m \rangle$，$m$ 为实数，则 $\langle l m | \hat{L}_z = m\hbar \langle l m |$，代入得：

$\langle \hat{L}_x \rangle = \frac{1}{i\hbar} [m\hbar \langle l m | \hat{L}_y | l m \rangle - m\hbar \langle l m | \hat{L}_y | l m \rangle] = 0$

同理 $\langle \hat{L}_y \rangle = 0$。

**例2．** $|l m\rangle$ 为 $(\hat{L}^2, \hat{L}_z)$ 的共同本征态，求 $\overline{\hat{L}_x^2}$，$\overline{\hat{L}_y^2}$。

$\overline{\hat{L}^2} = \langle l m | \hat{L}^2 | l m \rangle = \langle l m | l(l+1)\hbar^2 | l m \rangle = l(l+1)\hbar^2 = \langle l m | \hat{L}_z^2 | l m \rangle = \langle l m | m^2\hbar^2 | l m \rangle = m^2\hbar^2$

由 $\hat{L}_x = \frac{1}{i\hbar} [\hat{L}_y, \hat{L}_z] = \frac{1}{i\hbar} (\hat{L}_y \hat{L}_z - \hat{L}_z \hat{L}_y) = \frac{1}{i\hbar} (\hat{L}_y \hat{L}_z - \hat{L}_z \hat{L}_y)$

$\hat{L}_x^2 = \frac{1}{i\hbar} (\hat{L}_y \hat{L}_z \hat{L}_x - \hat{L}_z \hat{L}_y \hat{L}_x) = \frac{1}{i\hbar} ([\hat{L}_y, \hat{L}_z]\hat{L}_x + \hat{L}_z \hat{L}_y \hat{L}_x - \hat{L}_z \hat{L}_y \hat{L}_x) = \frac{1}{i\hbar} [\hat{L}_y, \hat{L}_z]\hat{L}_x$

$\overline{\hat{L}_x^2} = \langle l m | \hat{L}_x^2 | l m \rangle = \frac{1}{i\hbar} \langle l m | \hat{L}_y \hat{L}_z \hat{L}_x - \hat{L}_z \hat{L}_y \hat{L}_x | l m \rangle = \frac{1}{i\hbar} \langle l m | \hat{L}_y \hat{L}_z \hat{L}_x - \hat{L}_z \hat{L}_y \hat{L}_x | l m \rangle$

$\overline{\hat{L}_x^2} = \frac{1}{i\hbar} \langle l m | \hat{L}_y \hat{L}_z \hat{L}_x - \hat{L}_z \hat{L}_y \hat{L}_x | l m \rangle = \frac{1}{i\hbar} \langle l m | \hat{L}_y \hat{L}_z \hat{L}_x | l m \rangle - \frac{1}{i\hbar} \langle l m | \hat{L}_z \hat{L}_y \hat{L}_x | l m \rangle$

利用 $\hat{L}_z | l m \rangle = m\hbar | l m \rangle$ 及 $\langle l m | \hat{L}_z = m\hbar \langle l m |$：

$\overline{\hat{L}_x^2} = \frac{1}{i\hbar} [m\hbar \langle l m | \hat{L}_y \hat{L}_x | l m \rangle - m\hbar \langle l m | \hat{L}_y \hat{L}_x | l m \rangle] = 0$

由对称性 $\overline{\hat{L}_x^2} = \overline{\hat{L}_y^2} = \frac{1}{2}[\hat{L}^2 - \hat{L}_z^2] = \frac{1}{2}[l(l+1) - m^2]\hbar^2$

**方法：** 将本征态对应的算符尽量转化到最左/右边，直接作用到态矢上。

# 不确定度关系的严格证明

不确定度关系的严格证明

任意给定力学量A和B，对应的厄米算符为A和B，分别具有不确定度△A和△B，则有以下

A、B为厄米算符（⟨ψ|A−i⟨ψ|B）（A|ψ⟩+iB|ψ⟩）

对任意力学量A、B及量子态|ψ⟩，若A与B不对易即[A,B]≠0，则ΔA和ΔB不能同时为零，也即A与B不能同时测定。

任意给定力学量 $A$ 和 $B$，对应的厄米算符为 $\hat{A}$ 和 $\hat{B}$，分别具有不确定度 $\Delta A$ 和 $\Delta B$，则有以下关系：

$$\Delta A \Delta B \ge \frac{1}{2}|\langle[\hat{A},\hat{B}]\rangle|$$

其中 $\langle[\hat{A},\hat{B}]\rangle = \langle\psi|[\hat{A},\hat{B}]|\psi\rangle$ 对 $\forall|\psi\rangle$ 成立，$\Delta A = \hat{A} - \langle A\rangle$，$\Delta B = \hat{B} - \langle B\rangle$。

$$[\hat{A},\hat{B}] = [\Delta A + \langle A\rangle, \Delta B + \langle B\rangle] = (\Delta A + \langle A\rangle)(\Delta B + \langle B\rangle) - (\Delta B + \langle B\rangle)(\Delta A + \langle A\rangle) = [\Delta A, \Delta B]$$

$$\Delta A = \sqrt{\langle(\hat{A} - \langle A\rangle)^2\rangle}, \quad \Delta B = \sqrt{\langle(\hat{B} - \langle B\rangle)^2\rangle}$$

要证也即 $\langle(\hat{A} - \langle A\rangle)^2\rangle \cdot \langle(\hat{B} - \langle B\rangle)^2\rangle \ge \frac{1}{4}|\langle[\hat{A} - \langle A\rangle, \hat{B} - \langle B\rangle]\rangle|^2$

令 $\hat{x} = \hat{A} - \langle A\rangle$，$\hat{y} = \hat{B} - \langle B\rangle$，要证变为：$\langle\hat{x}^2\rangle \cdot \langle\hat{y}^2\rangle \ge \frac{1}{4}|\langle[\hat{x},\hat{y}]\rangle|^2$。联想 $b^2 \le 4ac$。

考虑 $|\phi\rangle = \xi|\hat{x}\psi\rangle + i|\hat{y}\psi\rangle$，$\langle\phi|\phi\rangle \ge 0$：

$$\langle\xi\hat{x}\psi + i\hat{y}\psi|\xi\hat{x}\psi + i\hat{y}\psi\rangle = (\xi\langle\psi|\hat{x}^\dagger + (-i)\langle\psi|\hat{y}^\dagger)(\xi\hat{x}|\psi\rangle + i\hat{y}|\psi\rangle)$$

$\hat{A}$、$\hat{B}$ 为厄米算符（$\hat{x}$、$\hat{y}$ 也为厄米算符）：

$$= (\xi\langle\psi|\hat{x} - i\langle\psi|\hat{y})(\xi\hat{x}|\psi\rangle + i\hat{y}|\psi\rangle)$$

$$= \xi^2\langle\psi|\hat{x}^2|\psi\rangle + \langle\psi|\hat{y}^2|\psi\rangle + i\xi(\langle\psi|\hat{x}\hat{y}|\psi\rangle - \langle\psi|\hat{y}\hat{x}|\psi\rangle) = \xi^2\langle\hat{x}^2\rangle + \langle\hat{y}^2\rangle + i\xi\langle[\hat{x},\hat{y}]\rangle$$

由 $\langle\phi|\phi\rangle \ge 0$，得 $\langle\hat{x}^2\rangle\langle\hat{y}^2\rangle \ge \frac{1}{4}|\langle[\hat{x},\hat{y}]\rangle|^2$，即 $\Delta A \cdot \Delta B \ge \frac{1}{2}|\langle[\hat{A},\hat{B}]\rangle|$。

> **结论**：对任意力学量 $A$、$B$，任意量子态 $|\psi\rangle$，若 $A$ 与 $B$ 不对易即 $[\hat{A},\hat{B}] \neq 0$，则 $\Delta A$ 和 $\Delta B$ 不能同时为零，也即 **$A$ 与 $B$ 不能同时测定**。

## 共同本征函数

设 $\hat{A}\psi_A = A\psi_A$，$\hat{B}\psi_B = B\psi_B$。若 $[\hat{A},\hat{B}] \neq 0$，则 $\psi_A$ 不是 $\hat{B}$ 的本征函数，$\psi_B$ 不是 $\hat{A}$ 的本征函数。

若 $[\hat{A},\hat{B}] = 0$，则可能存在 $\psi$，使 $\hat{A}\psi = A\psi$，$\hat{B}\psi = B\psi$。此时称 $\psi$ 为 $\hat{A}$ 和 $\hat{B}$ 的**共同本征函数**。

**定理**：设 $\hat{A}|k\rangle = a_k|k\rangle$，另有 $\hat{B}$，若 $[\hat{A},\hat{B}] = 0$，且 $a_k$ 不简并（即 $a_k$ 只对应一个本征态 $|k\rangle$），则 $|k\rangle$ 也是 $\hat{B}$ 的本征态，即 $\hat{A}$ 和 $\hat{B}$ 拥有共同本征态。

**证明**：$[\hat{A},\hat{B}] = 0 \Rightarrow \hat{A}\hat{B} = \hat{B}\hat{A}$。$\hat{B}\hat{A}|k\rangle = \hat{B} \cdot a_k|k\rangle = a_k\hat{B}|k\rangle$。则 $\hat{A}(\hat{B}|k\rangle) = a_k(\hat{B}|k\rangle)$，故 $\hat{B}|k\rangle$ 也是 $\hat{A}$ 属于本征值 $a_k$ 的本征态。因 $a_k$ 不简并，$\hat{B}|k\rangle$ 与 $|k\rangle$ 是同一个量子态，即 $\hat{B}|k\rangle = b_k|k\rangle$。故 $\hat{A}$、$\hat{B}$ 拥有共同本征态 $|k\rangle$。

**例**：$\psi_{\vec{p}}(\vec{r}) = \frac{1}{(2\pi\hbar)^{3/2}}e^{i\vec{p}\cdot\vec{r}/\hbar}$ 为 $\hat{p}_x, \hat{p}_y, \hat{p}_z$ 的共同本征函数，本征值为 $p_x, p_y, p_z$。$\hat{p}\psi_{\vec{p}}(\vec{r}) = \frac{\hbar}{i}\nabla\left(\frac{1}{(2\pi\hbar)^{3/2}}e^{i\vec{p}\cdot\vec{r}/\hbar}\right) = \vec{p}\,\psi_{\vec{p}}(\vec{r})$。

## 厄米算符本征值与本征态的特性

**转置算符**：对 $\Psi$ 和 $\Phi$，若 $\langle \Phi | A | \Psi \rangle = \langle \Psi | A^T | \Phi \rangle$，则称 $A$ 和 $A^T$ 互为彼此的转置算符。

**共轭算符**：对算符 $A$ 的每一项取复共轭，得到 $A^*$ 为 $A$ 的转置算符。

**厄米算符**：$A = A^\dagger = A^*$，则称 $A$ 为厄米算符。

**定理**：厄米算符 $A$ 在任意量子态下的平均值 $\bar{A}$ 为实数，$A^2$ 的平均值 $\overline{A^2} \ge 0$。

证明：
$$\langle \Psi | A | \Psi \rangle = \langle \Psi | A^\dagger | \Psi \rangle = \langle \Psi | A^* | \Psi \rangle = \langle \Psi^* | A | \Psi^* \rangle = (\langle \Psi | A | \Psi \rangle)^*$$
因 $A = A^*$，故 $\bar{A}$ 为实数。

或：$\langle \Psi | A^\dagger | \Psi \rangle = \langle A\Psi | \Psi \rangle$，$\langle \Psi | A | \Psi \rangle = \langle A\Psi | \Psi \rangle$，$A = A^\dagger = A^*$，$\bar{A}$ 为实数。

$$|\Psi\rangle = A|\Psi\rangle$$

$$\langle \Psi | A^2 | \Psi \rangle = \langle \Psi | AA | \Psi \rangle = \langle \Psi | A^\dagger A | \Psi \rangle = \langle A\Psi | A\Psi \rangle = \langle \Psi' | \Psi' \rangle \ge 0, \quad \overline{A^2} \ge 0$$

### 厄米算符本征值的实数性

设 $F|k\rangle = \lambda_k |k\rangle$，则 $\langle k | F | k \rangle = \bar{F} = \langle k | \lambda_k | k \rangle = \lambda_k \langle k | k \rangle = \lambda_k$，因 $\bar{F}$ 为实数，故 $\lambda_k$ 为实数。

### 厄米算符本征态的正交性与完备性、封闭性

**① 厄米算符属于不同本征值的本征态必然正交**（对不同 $|k\rangle$ 可能有不同的 $\lambda_k$）

设 $F|k\rangle = \lambda_k |k\rangle$，$F|k'\rangle = \lambda_{k'} |k'\rangle$。

$$\langle k' | F | k \rangle = \lambda_k \langle k' | k \rangle$$
$$\langle k' | F | k \rangle = \langle k' | F^\dagger | k \rangle = \langle F k' | k \rangle = \lambda_{k'}^* \langle k' | k \rangle$$

又 $\lambda_k$ 为实数，故 $\lambda_k^* = \lambda_k$，$\langle k' | F | k \rangle = \lambda_k \langle k' | k \rangle = \lambda_{k'} \langle k' | k \rangle$，而 $\lambda_k \ne \lambda_{k'}$，故 $\langle k' | k \rangle = 0$，即 $|k'\rangle$ 与 $|k\rangle$ 正交。

**② 本征态的完备性**

$P = |k\rangle \langle k|$ 为投影算符，$P = \sum_k P_k$。

若对 $\forall |\Psi\rangle$，有 $P|\Psi\rangle = \sum_k |k\rangle \langle k | \Psi \rangle = |\Psi\rangle$，则称基矢 $|k\rangle$ 具有完备性。（任意 $|\Psi\rangle$ 可按 $|k\rangle$ 展开）

记 $C_k = \langle k | \Psi \rangle$，则 $|\Psi\rangle = \sum_k |k\rangle \langle k | \Psi \rangle = \sum_k C_k |k\rangle$，$C_k$ 为用 $|k\rangle$ 将 $|\Psi\rangle$ 做展开时的展开系数。

**定理**：哈密顿算符 $H$ 为厄米算符，满足本征方程 $H|k\rangle = E_k |k\rangle$，对体系的任一归一化态 $|\Psi\rangle$，若 $\bar{H} = \langle \Psi | H | \Psi \rangle$ 有下界（总大于某常数）但无上界，则 $H$ 的本征态 $|k\rangle$ 的集合构成体系的一个完备集，即体系的任一量子态 $|\Psi\rangle$ 可用 $|k\rangle$ 来展开。

# 华中科技大学

IVERSITY OF SCIENCE AND TECHNOLOGY

## ③ 本征态的封闭性

£为单位算符，$V_4, \hat{E}|4\rangle = |4\rangle$。

若本征态或基矢 $|k\rangle$ 满足 $\sum_k |k\rangle\langle k| = \hat{E}$，称为本征态或基矢 $|k\rangle$ 的封闭性；$\sum_k \hat{P}_k = \sum_k |k\rangle\langle k| = \hat{E}$，称为投影算符 $\hat{P}_k$ 的封闭性。

**完备性与封闭性**：强调重点不同，完备性指任意 $|\psi\rangle$ 可按 $\{|k\rangle\}$ 展开，封闭性指数学上封闭性方程 $\sum_k |k\rangle\langle k| = \hat{I}$ 成立，两者相互依存。

**例**：设体系的能量本征方程为 $\hat{H}|k\rangle = E_k|k\rangle$，证明哈密顿算符可表示为 $\hat{H} = \sum_k E_k |k\rangle\langle k|$（本征态具有完备性、封闭性）。

$\hat{H}|k\rangle\langle k| = E_k|k\rangle\langle k|$，则 $\sum_k \hat{H}|k\rangle\langle k| = \hat{H}\sum_k |k\rangle\langle k| = \sum_k E_k|k\rangle\langle k|$，从而有 $\hat{H}\hat{I} = \hat{H} = \sum_k E_k|k\rangle\langle k|$。

## 守恒量与能级简并度

### 力学量平均值的时间依赖特性

$\bar{A}(t) = \langle\psi(t)|\hat{A}|\psi(t)\rangle$。薛定谔方程：$i\hbar\frac{\partial}{\partial t}|\psi(t)\rangle = \hat{H}|\psi\rangle$。在左矢空间中：$-i\hbar\frac{\partial}{\partial t}\langle\psi| = \langle\psi|\hat{H}$（$\hat{H}^\dagger = \hat{H}$）。

$\frac{d\bar{A}}{dt} = \frac{d}{dt}\left(\langle\psi|\hat{A}|\psi\rangle\right) = \langle\frac{\partial\psi}{\partial t}|\hat{A}|\psi\rangle + \langle\psi|\frac{\partial\hat{A}}{\partial t}|\psi\rangle + \langle\psi|\hat{A}|\frac{\partial\psi}{\partial t}\rangle = -\frac{1}{i\hbar}\langle\psi|\hat{H}\hat{A}|\psi\rangle + \langle\psi|\frac{\partial\hat{A}}{\partial t}|\psi\rangle + \frac{1}{i\hbar}\langle\psi|\hat{A}\hat{H}|\psi\rangle$

$\frac{d\bar{A}}{dt} = \frac{1}{i\hbar}\langle\psi|[\hat{A},\hat{H}]|\psi\rangle + \langle\psi|\frac{\partial\hat{A}}{\partial t}|\psi\rangle$，若 $\frac{\partial\hat{A}}{\partial t} = 0$（$\hat{A}$ 不显含 $t$）且 $[\hat{A},\hat{H}] = 0$，则 $\frac{d\bar{A}}{dt} = 0$，$\bar{A}$ 与时间无关。

$\hat{A}$ 在任何态 $\psi(t)$ 下的平均值 $\bar{A}$ 都不随时间改变。

### 守恒量

$\hat{A}$ 在任何态 $\psi(t)$ 下的平均值 $\bar{A}$ 都不随 $t$ 改变，则称此时 $\hat{A}$ 对应的力学量为体系的一个**守恒量**。

$\frac{\partial\hat{A}}{\partial t} = 0$ 且 $[\hat{A},\hat{H}] = 0 \Rightarrow \hat{A}$ 为守恒量。

**定理**：若 $[\hat{F},\hat{H}] = 0$，$[\hat{G},\hat{H}] = 0$，但 $[\hat{F},\hat{G}] \neq 0$，则体系的能级是简并的。（$\hat{F}$、$\hat{G}$ 为守恒量）

$\hat{F}$、$\hat{H}$ 有共同本征函数 $\psi$：$\hat{F}\psi = F\psi$，$\hat{H}\psi = E\psi$。$[\hat{G},\hat{H}] = 0$，则 $\hat{H}(\hat{G}\psi) = \hat{G}\hat{H}\psi = \hat{G}(E\psi) = E(\hat{G}\psi)$。

又 $\hat{G}\hat{F}\psi = \hat{F}\hat{G}\psi \neq F\hat{G}\psi$，则 $\hat{G}\psi$ 不是 $\hat{F}$ 的本征态，$\hat{G}\psi$ 和 $\psi$ 不是一个态，即 $E$ 对应至少两个态，**能级简并**。

# 表象变换与矩阵力学

设 $F=(A_1,A_2,\dots,A_n)$ 是一组力学量完全集，$|k\rangle$ 是共同本征态，其中 $k$ 表征所有量子数。$|k\rangle$ 是正交归一的，满足 $\langle k|m\rangle=\delta_{km}$（$k\neq m$ 时为 0），$|k\rangle$ 是完备的，即体系中任一量子态可按 $|k\rangle$ 展开。

$\{|k\rangle\}$ 构成一个表象，可称为 $F$ 表象，$F$ 构成无穷维的希尔伯特空间，量子态 $|\psi\rangle$ 是希尔伯特空间中的一个矢量。$|\psi\rangle=\sum_k a_k|k\rangle$，则 $a_k=\langle k|\psi\rangle$ 为内积，也可视为"投影"。

## 表象间的转化

$F$ 表象中，$|k\rangle$ 为基矢，$|\psi\rangle=\sum_k a_k|k\rangle$，$|\psi\rangle$ 在 $F$ 表象中可用系数列向量表示为 $a=\begin{pmatrix}a_1\\a_2\\\vdots\end{pmatrix}$。

另一 $F'$ 表象中，$|\beta\rangle$ 为基矢，$|\psi\rangle=\sum_\beta a_\beta|\beta\rangle$，在 $F'$ 表象中可表示为 $a'=\begin{pmatrix}a_1'\\a_2'\\\vdots\end{pmatrix}$。

$a'$ 与 $a$ 的转化实际上是基矢之间的转化。

$|\psi\rangle=\sum_k a_k|k\rangle=\sum_\beta b_\beta|\beta\rangle$，$|k\rangle=\sum_\beta \langle\beta|k\rangle|\beta\rangle$（$|k\rangle$ 按 $|\beta\rangle$ 展开），从而统一基矢为 $|\beta\rangle$。

记 $S_{\beta k}=\langle\beta|k\rangle$，$S=(S_{\beta k})$，

则 $a_\beta=\sum_k a_k\langle\beta|k\rangle$，$a'=Sa$，即 $a'_\beta=\sum_k S_{\beta k}a_k$。

$S^\dagger S=SS^\dagger=I$，即 $S$ 为幺正矩阵。

**注**：$a$、$a'$ 均为系数列向量，与本征态形式相似但意义完全不同。$|k\rangle$ 在希尔伯特空间中可表示为一个列向量，$|\psi\rangle$ 按 $|k\rangle$ 展开所得系数列为 $a$。

从矢量的角度考虑，$|\psi\rangle=(e_1,e_2,\dots,e_n,\dots)\begin{pmatrix}a_1\\a_2\\\vdots\end{pmatrix}$，即列向量 $e_i$ 的线性组合系数列。

要"消去" $(e_1',e_2',\dots,e_n',\dots)$，则 $(e_1,e_2,\dots,e_n,\dots)=(e_1',e_2',\dots,e_n',\dots)S$，其中

$$S=\begin{pmatrix}S_{11}&S_{12}&\dots&S_{1k}&\dots\\S_{21}&S_{22}&\dots&S_{2k}&\dots\\\vdots&\vdots&&\vdots&\\S_{k1}&S_{k2}&\dots&S_{kk}&\dots\\\vdots&\vdots&&\vdots&\end{pmatrix}$$

$\langle k'|k\rangle=S_{k'k}$，$\langle k|k\rangle=1$，$|k\rangle=\sum_\beta S_{\beta k}|\beta\rangle$，$\langle k|k\rangle=\left(\sum_\beta S_{\beta k}^*\langle\beta|\right)\left(\sum_\beta S_{\beta k}|\beta\rangle\right)=\sum_\beta |S_{\beta k}|^2=1$。

$\langle m|k\rangle=\left(\sum_\beta S_{\beta m}^*\langle\beta|\right)\left(\sum_\beta S_{\beta k}|\beta\rangle\right)=\sum_\beta S_{\beta m}^*S_{\beta k}=\delta_{mk}$。

即 $S^\dagger S=I$，**$S$ 为幺正矩阵**。

$(e_1,e_2,\dots,e_n,\dots)=(e_1',e_2',\dots,e_n',\dots)\begin{pmatrix}(e_1',e_1)&(e_1',e_2)&\dots\\(e_2',e_1)&(e_2',e_2)&\dots\\\vdots&\vdots&\end{pmatrix}=(e_1',e_2',\dots)S$。

即 $S^\dagger S=I$，**$S$ 为幺正矩阵**。

$(e_1,e_2,\dots,e_n,\dots)=(e_1',e_2',\dots,e_n',\dots)\begin{pmatrix}(e_1',e_1)&(e_1',e_2)&\dots\\(e_2',e_1)&(e_2',e_2)&\dots\\\vdots&\vdots&\end{pmatrix}=(e_1',e_2',\dots)S$。

从矢量的角度考虑，$|k\rangle=\sum_{\beta} S_{\beta k}|\beta\rangle$，其中 $S_{\beta k}=\langle\beta|k\rangle$。由于 $\langle k'|k\rangle=\delta_{k'k}$，且 $\langle\beta|\alpha\rangle=\delta_{\beta\alpha}$，则

$$
\langle k'|k\rangle=\sum_{\alpha,\beta} S_{\alpha k'}^* S_{\beta k}\langle\alpha|\beta\rangle=\sum_{\alpha} S_{\alpha k'}^* S_{\alpha k}=\delta_{k'k},
$$

即 $S^\dagger S=I$，故 $S$ 为幺正矩阵。

基矢变换可写为 $(e_1,e_2,\dots)=(e_1',e_2',\dots)S$，其中矩阵元 $S_{ij}=\langle e_i'|e_j\rangle$。

Ssi S22…Sok…
Sp+S2-Sk…)
S为么正矩阵
(ei,ei)(t.e)(ei.ep)…
华中科技大学附

A.B为厄米算符（乡＜41A-i<41B)(§A14>+iB14>)

真＝[mt<(m|G|(m>-<|m|G|(m>]．六及＝瓦＝0

A在任何态4(t）下的平均值A都不随时间改变

例1．求以和ly在1(m＞下的平均值．

也是B的本征态，即A和B拥有共同本征态

R.China 中国．武汉 T

称为投影算符成的封闭性．