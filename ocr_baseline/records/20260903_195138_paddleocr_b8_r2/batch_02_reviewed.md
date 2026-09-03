# 科技

## 常见对易恒等式

$$[A, B] = -[B, A]$$

$$[A, B+C] = [A, B] + [A, C]$$

$$[A, BC] = [A, B]C + B[A, C]$$

$$[AB, C] = A[B, C] + [A, C]B$$

$$[A, B+C] + [B, A+C] + [C, A+B] = 0$$

$$[A, [B, C]] + [B, [C, A]] + [C, [A, B]] = 0 \quad (\text{对称})$$

## 利用对易关系求解平均值问题

**例1.** 求 $\hat{l}_x$ 和 $\hat{l}_y$ 在 $|lm\rangle$ 下的平均值。

已知 $\hat{l}_z |lm\rangle = m\hbar |lm\rangle$，$[\hat{l}_y, \hat{l}_z] = i\hbar \hat{l}_x$，$[\hat{l}_z, \hat{l}_x] = i\hbar \hat{l}_y$，从而可用含 $\hat{l}_z$ 的表达式表出 $\hat{l}_x$、$\hat{l}_y$。

$$\bar{l}_x = \langle lm|\hat{l}_x|lm\rangle = \langle lm|[\hat{l}_y, \hat{l}_z]|lm\rangle = \frac{1}{i\hbar}[\langle lm|\hat{l}_y \hat{l}_z|lm\rangle - \langle lm|\hat{l}_z \hat{l}_y|lm\rangle]$$

由 $\hat{l}_z |lm\rangle = m\hbar |lm\rangle$，$m$ 为实数，则 $\langle lm|\hat{l}_z = m\hbar \langle lm|$。

$$\therefore \bar{l}_x = \frac{1}{i\hbar}[m\hbar \langle lm|\hat{l}_y|lm\rangle - m\hbar \langle lm|\hat{l}_y|lm\rangle] = 0$$

$$\therefore \bar{l}_x = 0$$

同理可得 $\bar{l}_y = 0$。

**例2.** $|lm\rangle$ 为 $\hat{l}^2$、$\hat{l}_z$ 的共同本征态，求 $\overline{l_x^2}$、$\overline{l_y^2}$。

$$\overline{l_x^2} = \langle lm|\hat{l}_x^2|lm\rangle = \langle lm|(\hat{l}^2 - \hat{l}_z^2)|lm\rangle = [l(l+1) - m^2]\hbar^2$$

$$\overline{l_y^2} = \langle lm|\hat{l}_y^2|lm\rangle = \langle lm|(\hat{l}^2 - \hat{l}_z^2)|lm\rangle = [l(l+1) - m^2]\hbar^2$$

利用 $[\hat{l}_x, \hat{l}_y] = i\hbar \hat{l}_z$ 及 $\hat{l}_x^2 + \hat{l}_y^2 = \hat{l}^2 - \hat{l}_z^2$ 可进一步验证。

**方法：** 将本征态对应的算符尽量转化到最左/右边，直接作用到态矢上。

## 不确定度关系的严格证明

任意给定力学量 $A$ 和 $B$，对应的厄米算符为 $\hat{A}$ 和 $\hat{B}$，分别具有不确定度 $\Delta A$ 和 $\Delta B$，则有以下关系：

$$\Delta A \cdot \Delta B \geq \frac{1}{2}|\langle[\hat{A}, \hat{B}]\rangle|$$

其中 $\Delta A = \sqrt{\langle \hat{A}^2 \rangle - \langle \hat{A} \rangle^2}$，$\Delta B = \sqrt{\langle \hat{B}^2 \rangle - \langle \hat{B} \rangle^2}$。

令 $x = \hat{A} - \langle \hat{A} \rangle$，$y = \hat{B} - \langle \hat{B} \rangle$，要证变为 $\overline{x^2} \cdot \overline{y^2} \geq \frac{1}{4}|\langle[x, y]\rangle|^2$，联想 $b^2 \geq 4ac$。

考虑 $|\phi\rangle = (\alpha \hat{x} + i\hat{y})|\psi\rangle$，$\langle\phi|\phi\rangle \geq 0$：

$$\langle\phi|\phi\rangle = \langle\psi|(\alpha \hat{x} - i\hat{y})(\alpha \hat{x} + i\hat{y})|\psi\rangle = \alpha^2 \langle\hat{x}^2\rangle + \langle\hat{y}^2\rangle + i\alpha\langle[\hat{x}, \hat{y}]\rangle \geq 0$$

$\because \forall \alpha$，$\langle\phi|\phi\rangle \geq 0$，$\therefore \langle[\hat{x}, \hat{y}]\rangle^2 \leq 4\langle\hat{x}^2\rangle\langle\hat{y}^2\rangle$，即 $\overline{x^2} \cdot \overline{y^2} \geq \frac{1}{4}|\langle[\hat{x}, \hat{y}]\rangle|^2$。

$$\Rightarrow \Delta A \cdot \Delta B \geq \frac{1}{2}|\langle[\hat{A}, \hat{B}]\rangle|$$

**注意：** 对任意力学量 $A$、$B$，任意量子态 $|\psi\rangle$，若 $A$ 与 $B$ 不对易即 $[\hat{A}, \hat{B}] \neq 0$，则 $\Delta A$ 和 $\Delta B$ 不能同时为零，也即 $A$ 与 $B$ 不能同时测定。

## 共同本征函数

设 $\hat{A}\psi_a = A_a \psi_a$，$\hat{B}\psi_b = B_b \psi_b$。若 $[\hat{A}, \hat{B}] \neq 0$，则 $\psi_a$ 不是 $\hat{B}$ 的本征函数，$\psi_b$ 不是 $\hat{A}$ 的本征函数。

若 $[\hat{A}, \hat{B}] = 0$，则可能存在 $\psi$，使 $\hat{A}\psi = A\psi$，$\hat{B}\psi = B\psi$，此时称 $\psi$ 为 $A$ 和 $B$ 的共同本征函数。

**定理：** 设 $\hat{A}|k\rangle = a_k |k\rangle$，另有 $\hat{B}$，若 $[\hat{A}, \hat{B}] = 0$，且 $a_k$ 不简并（即 $a_k$ 只对应一个本征态 $|k\rangle$），则 $|k\rangle$ 也是 $\hat{B}$ 的本征态，即 $A$ 和 $B$ 拥有共同本征态。

**证明：** $[\hat{A}, \hat{B}] = 0 \Rightarrow \hat{A}\hat{B} = \hat{B}\hat{A}$，$\hat{B}\hat{A}|k\rangle = \hat{B} \cdot a_k |k\rangle = a_k \hat{B}|k\rangle$。则 $\hat{A}(\hat{B}|k\rangle) = a_k(\hat{B}|k\rangle)$，$\therefore \hat{B}|k\rangle$ 也是 $A$ 属于本征值 $a_k$ 的本征态，故 $\hat{B}|k\rangle$ 与 $|k\rangle$ 是同一个量子态，即 $\hat{B}|k\rangle = b_k |k\rangle$。$A$、$B$ 拥有共同本征态 $|k\rangle$。

**例：** $\psi(\vec{r}) = \frac{1}{(2\pi\hbar)^{3/2}} e^{i\vec{p}\cdot\vec{r}/\hbar}$ 是 $\hat{p}_x$、$\hat{p}_y$、$\hat{p}_z$ 的共同本征函数，本征值为 $p_x$、$p_y$、$p_z$。

## 厄米算符本征值与本征态的特性

**转置算符：** 对 $\forall\psi$ 和 $\varphi$，若 $\langle\psi|\hat{A}|\varphi\rangle = \langle\varphi|\hat{A}|\psi\rangle$，则称 $\hat{A}$ 和 $\hat{A}^T$ 互为彼此的转置算符。

**共轭算符：** 对算符 $\hat{A}$ 的每一元素取复共轭，得到 $\hat{A}^*$ 为 $\hat{A}$ 的共轭算符。

**厄米算符：** $\hat{A} = \hat{A}^\dagger = (\hat{A}^*)^T$，则称 $\hat{A}$ 为厄米算符。

**定理：** 厄米算符 $\hat{A}$ 在任意量子态下的平均值 $\bar{A}$ 为实数，$\hat{A}^\dagger$ 的平均值 $\overline{A^\dagger} \geq 0$。

$$\langle\psi|\hat{A}|\psi\rangle = \langle\psi|\hat{A}^\dagger|\psi\rangle = \langle\psi|\hat{A}|\psi\rangle^* = \langle\psi|\hat{A}|\psi\rangle \quad \therefore \bar{A} = \bar{A}^*，\bar{A} 为实数$$

$$\langle\psi|\hat{A}^2|\psi\rangle = \langle\psi|\hat{A}\hat{A}|\psi\rangle = \langle\hat{A}\psi|\hat{A}\psi\rangle = \langle\varphi|\varphi\rangle \geq 0，\quad |\varphi\rangle = \hat{A}|\psi\rangle$$

### 厄米算符本征值的实数性

$$\hat{F}|k\rangle = \lambda_k |k\rangle，则 \langle k|\hat{F}|k\rangle = \bar{F} = \langle k|\lambda_k |k\rangle = \lambda_k \langle k|k\rangle = \lambda_k，\therefore \lambda_k = \bar{F} 为实数$$

### 厄米算符本征态的正交性与完备性、封闭性

**① 厄米算符属于不同本征值的本征态必然正交**（对不同 $|k\rangle$ 可能有不同的 $\lambda$）：

$$\hat{F}|k\rangle = \lambda_k |k\rangle，\hat{F}|k'\rangle = \lambda_{k'} |k'\rangle$$

$$\langle k'|\hat{F}|k\rangle = \lambda_k \langle k'|k\rangle，\quad \langle k'|\hat{F}|k\rangle = \langle k'|\hat{F}^\dagger|k\rangle = \lambda_{k'} \langle k'|k\rangle$$

又 $\lambda_k$ 为实数，$\therefore \lambda_k = \lambda_k^*$，$\lambda_k \langle k'|k\rangle = \lambda_{k'} \langle k'|k\rangle$，而 $\lambda_k \neq \lambda_{k'}$，$\therefore \langle k'|k\rangle = 0$，即 $|k\rangle$ 与 $|k'\rangle$ 正交。

**② 本征态的完备性：**

$\hat{P}_k = |k\rangle\langle k|$ 为投影算符，$\hat{P}_k = \hat{P}_k^\dagger$。

若对 $\forall|\psi\rangle$，有 $\sum_k \hat{P}_k |\psi\rangle = \sum_k |k\rangle\langle k|\psi\rangle = |\psi\rangle$，则称基矢 $|k\rangle$ 具有完备性（任意 $|\psi\rangle$ 可按 $|k\rangle$ 展开）。

记 $c_k = \langle k|\psi\rangle$，则 $|\psi\rangle = \sum_k |k\rangle\langle k|\psi\rangle = \sum_k c_k |k\rangle$，$c_k$ 为用 $|k\rangle$ 将 $|\psi\rangle$ 做展开时的展开系数。

**定理：** 哈密顿算符 $\hat{H}$ 为厄米算符，满足本征方程 $\hat{H}|k\rangle = E_k |k\rangle$。对体系的任一归一化态 $\Phi$，若 $\bar{H} = \langle\Phi|\hat{H}|\Phi\rangle$ 有下界（总大于某常数）但无上界，则 $\hat{H}$ 的本征态 $|k\rangle$ 的集合构成体系的一个完备集，即体系的任一量子态 $|\psi\rangle$ 可用 $|k\rangle$ 来展开。

## 一维谐振子

$$V(x) = \frac{1}{2}kx^2 = \frac{1}{2}\mu\omega^2 x^2 \quad (-\frac{dV}{dx} = -kx = m\ddot{x}，\ddot{x} + \omega^2 x = 0，\omega^2 = \frac{k}{\mu})$$

薛定谔方程：

$$-\frac{\hbar^2}{2\mu}\frac{d^2\psi(x)}{dx^2} + \frac{1}{2}\mu\omega^2 x^2 \psi(x) = E\psi(x)$$

令 $\alpha = \sqrt{\frac{\mu\omega}{\hbar}}$，$\xi = \alpha x$，$\psi(x) = \varphi(\xi)$，则方程化为：

$$\frac{d^2\varphi(\xi)}{d\xi^2} + (\lambda - \xi^2)\varphi(\xi) = 0$$

为“消除”$\xi^2$ 项，试探设 $\varphi(\xi) = e^{-\xi^2/2}H(\xi)$，代入得：

$$\frac{d^2H(\xi)}{d\xi^2} - 2\xi\frac{dH(\xi)}{d\xi} + (\lambda - 1)H(\xi) = 0$$

$\varphi(\xi)$ 有界，仅当 $\lambda = 2n + 1$ 时，$H_n(\xi)$ 有有限解，$H_n(\xi) = (-1)^n e^{\xi^2}\frac{d^n}{d\xi^n}e^{-\xi^2}$（厄米多项式）。

正交归一性：$\int_{-\infty}^{\infty} H_n(\xi)H_m(\xi)e^{-\xi^2}d\xi = \sqrt{\pi}2^n n! \delta_{nm}$

$$\varphi_n(\xi) = N_n e^{-\xi^2/2}H_n(\xi)，\quad N_n = \sqrt{\frac{\alpha}{\sqrt{\pi}2^n n!}}$$

**能量分立化：**

$$E_n = \left(n + \frac{1}{2}\right)\hbar\omega，\quad \psi_n(x) = N_n e^{-\alpha^2 x^2/2} H_n(\alpha x)$$

### 补充：方程 $\frac{d^2H(\xi)}{d\xi^2} - 2\xi\frac{dH(\xi)}{d\xi} + (\lambda - 1)H(\xi) = 0$ 的两种解法

**① 幂级数解法，构造递推的系数关系：**

设 $H(\xi) = \sum_j a_j \xi^j$，代入得递推关系：

$$(j+2)(j+1)a_{j+2} - 2j a_j + (\lambda - 1)a_j = 0$$

$$\Rightarrow a_{j+2} = \frac{2j - (\lambda - 1)}{(j+2)(j+1)}a_j$$

$\varphi(\xi)$ 按 $e^{\xi^2}$ 量级增长，不可积。级数存在（只有）有限项：$a_n \neq 0$，$a_{n+2} = 0$，即 $\lambda = 2n + 1$。

从而有 $a_{j+2} = \frac{2(j-n)}{(j+2)(j+1)}a_j$，多项式 $H(\xi)$ 只能含奇数项或偶数项，系数由高次项推至低次项。

方程可变化为 $\frac{d^2H_n(\xi)}{d\xi^2} - 2\xi\frac{dH_n(\xi)}{d\xi} + 2nH_n(\xi) = 0$，其解为厄米多项式 $H_n(\xi)$。

$$H_n(\xi) = \sum_{k=0}^{\lfloor n/2 \rfloor} \frac{(-1)^k n!}{k!(n-2k)!}(2\xi)^{n-2k}$$

$H_n(\xi)$ 满足：$H_n'(\xi) - 2\xi H_n'(\xi) + 2nH_n(\xi) = 0$，母函数 $w(t, x) = e^{2tx - t^2}$，$\frac{\partial w(t,x)}{\partial t} + 2(t-x)w(t,x) = 0$。

### 本征态的封闭性

$\hat{I}$ 为单位算符，$\hat{I}|\psi\rangle = |\psi\rangle$。

若本征态或基矢 $|k\rangle$ 满足 $\sum_k |k\rangle\langle k| = \hat{I}$，称为本征态或基矢 $|k\rangle$ 的封闭性；$\sum_k \hat{P}_k = \sum_k |k\rangle\langle k| = \hat{I}$ 称为投影算符的封闭性。

**完备性 & 封闭性：** 强调重点不同，完备性指任意 $|\psi\rangle$ 可按 $\{|k\rangle\}$ 展开，封闭性指数学上封闭性方程 $\sum_k |k\rangle\langle k| = \hat{I}$ 成立，两者相互依存。

**例：** 设体系的能量本征方程为 $\hat{H}|k\rangle = E_k |k\rangle$，证明哈密顿算符可表示为 $\hat{H} = \sum_k E_k |k\rangle\langle k|$（本征态具有完备性、封闭性）。

$$\hat{H}\sum_k |k\rangle\langle k| = \sum_k E_k |k\rangle\langle k|，则 \hat{H} = \hat{H}\sum_k |k\rangle\langle k| = \sum_k E_k |k\rangle\langle k|$$

## 守恒量与能级简并度

### 力学量平均值的时间依赖特性

$$\bar{A}(t) = \langle\psi(t)|\hat{A}|\psi(t)\rangle，薛定谔方程：i\hbar\frac{\partial}{\partial t}|\psi(t)\rangle = \hat{H}|\psi(t)\rangle$$

在左矢空间中：$-i\hbar\frac{\partial}{\partial t}\langle\psi| = \langle\psi|\hat{H}$。

$$\frac{d\bar{A}}{dt} = \frac{\partial}{\partial t}\langle\psi|\hat{A}|\psi\rangle + \langle\psi|\frac{\partial\hat{A}}{\partial t}|\psi\rangle + \langle\psi|\hat{A}\frac{\partial}{\partial t}|\psi\rangle = -\frac{1}{i\hbar}\langle\psi|\hat{H}\hat{A}|\psi\rangle + \langle\psi|\frac{\partial\hat{A}}{\partial t}|\psi\rangle + \frac{1}{i\hbar}\langle\psi|\hat{A}\hat{H}|\psi\rangle$$

$$= \frac{1}{i\hbar}\langle\psi|[\hat{A}, \hat{H}]|\psi\rangle + \langle\psi|\frac{\partial\hat{A}}{\partial t}|\psi\rangle$$

若 $\frac{\partial\hat{A}}{\partial t} = 0$（$\hat{A}$ 不显含 $t$）且 $[\hat{A}, \hat{H}] = 0$，则 $\frac{d\bar{A}}{dt} = 0$，$\bar{A}$ 与时间无关，$\hat{A}$ 在任何态 $|\psi(t)\rangle$ 下的平均值 $\bar{A}$ 都不随时间改变。

### 守恒量

$\hat{A}$ 在任何态 $|\psi(t)\rangle$ 下的平均值 $\bar{A}$ 都不随 $t$ 改变，则称此时 $\hat{A}$ 对应的力学量为体系的一个守恒量。

$$\frac{\partial\hat{A}}{\partial t} = 0 \text{ 且 } [\hat{A}, \hat{H}] = 0 \Rightarrow \hat{A} \text{ 为守恒量}$$

**定理：** 若 $[\hat{F}, \hat{H}] = 0$，$[\hat{G}, \hat{H}] = 0$，但 $[\hat{F}, \hat{G}] \neq 0$，则体系的能级是简并的。（$F$、$G$ 为守恒量）

**证明：** $\hat{H}$ 有共同本征函数 $\psi$，$\hat{F}\psi = F\psi$，$\hat{H}\psi = E\psi$。$\because [\hat{G}, \hat{H}] = 0$，则 $\hat{H}(\hat{G}\psi) = \hat{G}\hat{H}\psi = E(\hat{G}\psi)$。又 $\hat{F}(\hat{G}\psi) \neq F(\hat{G}\psi)$，则 $\hat{G}\psi$ 不是 $\hat{F}$ 的本征态，$\therefore \hat{G}\psi$ 和 $\psi$ 不是一个态，即 $E$ 对应至少两个态，能级简并。

# 表象变换与矩阵力学

设 $\hat{F} = (\hat{A}_1, \hat{A}_2, \ldots, \hat{A}_n)$ 是一组力学量完全集，$|k\rangle$ 是其共同本征态，其中 $k$ 表征所有量子数。

$\{|k\rangle\}$ 是正交归一的，满足 $\langle k|m\rangle = \delta_{km}$，$\{|k\rangle\}$ 是完备的，即体系中任一量子态可按 $|k\rangle$ 展开。

$\{|k\rangle\}$ 构成一个表象，可称为 $F$ 表象。$F$ 构成无穷维的希尔伯特空间，量子态是希尔伯特空间中的一个矢量，$|\psi\rangle = \sum_k a_k |k\rangle$，则 $a_k = \langle k|\psi\rangle$ 为内积，也可视为投影。

## 表象间的转化

$F$ 表象中，$|k\rangle = e_k$，$|\psi\rangle = \sum_k a_k |k\rangle$，$|\psi\rangle$ 在 $F$ 表象中可用系数列向量表示为 $a$。

$a'$ 与 $a$ 的转化实际上是基矢之间的转化。

\$\$|\psi\rangle = \sum_k a_k |k\rangle = \sum_\beta a'_\beta |\beta\rangle，\quad |k\rangle = \sum_\beta \langle\beta|k\rangle \cdot |\beta\rangle \quad (|k\rangle \