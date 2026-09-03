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

由 $\hat{l}_z |lm\rangle = m\hbar |lm\rangle$，$m$ 为实数，则 $\langle lm|\hat{l}_z = m\hbar \langle lm|$，

$$\therefore \bar{l}_x = \frac{1}{i\hbar}[m\hbar \langle lm|\hat{l}_y|lm\rangle - m\hbar \langle lm|\hat{l}_y|lm\rangle] = 0$$

$$\therefore \bar{l}_x = 0$$

同理 $\bar{l}_y = 0$。

**例2.** $|lm\rangle$ 为 $\hat{l}^2$、$\hat{l}_z$ 的共同本征态，求 $\overline{l_x^2}$、$\overline{l_y^2}$。

$$\overline{l_x^2} = \langle lm|\hat{l}_x^2|lm\rangle = \langle lm|(\hat{l}^2 - \hat{l}_z^2)|lm\rangle = [l(l+1) - m^2]\hbar^2$$

$$\overline{l_y^2} = \langle lm|\hat{l}_y^2|lm\rangle = \langle lm|(\hat{l}^2 - \hat{l}_z^2)|lm\rangle = [l(l+1) - m^2]\hbar^2$$

利用 $\hat{l}_x \hat{l}_y - \hat{l}_y \hat{l}_x = [\hat{l}_x, \hat{l}_y] = i\hbar \hat{l}_z$，以及 $\hat{l}_x^2 + \hat{l}_y^2 = \hat{l}^2 - \hat{l}_z^2$，可得：

$$\overline{l_x^2} = \overline{l_y^2} = \frac{1}{2}[\langle lm|\hat{l}^2|lm\rangle - \langle lm|\hat{l}_z^2|lm\rangle] = \frac{1}{2}[l(l+1) - m^2]\hbar^2$$

**方法：** 将本征态对应的算符尽量转化到最左/右边，直接作用到态矢上。

## 不确定度关系的严格证明

任意给定力学量 $A$ 和 $B$，对应的厄米算符为 $\hat{A}$ 和 $\hat{B}$，分别具有不确定度 $\Delta A$ 和 $\Delta B$，则有以下关系：

$$\Delta A \cdot \Delta B \geq \frac{1}{2}|\langle[\hat{A}, \hat{B}]\rangle|$$

其中 $\langle[\hat{A}, \hat{B}]\rangle = \langle \psi|[\hat{A}, \hat{B}]|\psi\rangle$ 对任意态成立，$\Delta A = \sqrt{\langle\hat{A}^2\rangle - \langle\hat{A}\rangle^2}$，$\Delta B = \sqrt{\langle\hat{B}^2\rangle - \langle\hat{B}\rangle^2}$。

也即：

$$[\hat{A}, \hat{B}] = [\Delta\hat{A} + \langle\hat{A}\rangle, \Delta\hat{B} + \langle\hat{B}\rangle] = (\Delta\hat{A} + \langle\hat{A}\rangle)(\Delta\hat{B} + \langle\hat{B}\rangle) - (\Delta\hat{B} + \langle\hat{B}\rangle)(\Delta\hat{A} + \langle\hat{A}\rangle) = [\Delta\hat{A}, \Delta\hat{B}]$$

$$\Delta A = \sqrt{\langle\hat{A}^2\rangle - \langle\hat{A}\rangle^2} = \sqrt{\langle(\hat{A} - \langle\hat{A}\rangle)^2\rangle}$$

要证：

$$\langle(\hat{A} - \langle\hat{A}\rangle)^2\rangle \cdot \langle(\hat{B} - \langle\hat{B}\rangle)^2\rangle \geq \frac{1}{4}|\langle[\hat{A} - \langle\hat{A}\rangle, \hat{B} - \langle\hat{B}\rangle]\rangle|^2$$

令 $\hat{X} = \hat{A} - \langle\hat{A}\rangle$，$\hat{Y} = \hat{B} - \langle\hat{B}\rangle$，要证变为：

$$\langle\hat{X}^2\rangle \cdot \langle\hat{Y}^2\rangle \geq \frac{1}{4}|\langle[\hat{X}, \hat{Y}]\rangle|^2$$

联想 $b^2 \geq 4ac$。

考虑 $|\phi\rangle = (\hat{X} + i\lambda\hat{Y})|\psi\rangle$，$\langle\phi|\phi\rangle \geq 0$：

$$\langle\phi|\phi\rangle = \langle\psi|(\hat{X} + i\lambda\hat{Y})^\dagger(\hat{X} + i\lambda\hat{Y})|\psi\rangle = \langle\psi|(\hat{X} - i\lambda\hat{Y})(\hat{X} + i\lambda\hat{Y})|\psi\rangle$$

$\hat{X}$、$\hat{Y}$ 为厄米算符：

$$= \lambda^2\langle\psi|\hat{X}^2|\psi\rangle + \langle\psi|\hat{Y}^2|\psi\rangle + i\lambda\langle\psi|[\hat{X}, \hat{Y}]|\psi\rangle$$

$$= \lambda^2\langle\hat{X}^2\rangle + \langle\hat{Y}^2\rangle + i\lambda\langle[\hat{X}, \hat{Y}]\rangle$$

$\because \forall \lambda$，$\langle\phi|\phi\rangle \geq 0$，$\therefore \langle[\hat{X}, \hat{Y}]\rangle^2 \leq 4\langle\hat{X}^2\rangle \cdot \langle\hat{Y}^2\rangle$，即：

$$\langle\hat{X}^2\rangle \cdot \langle\hat{Y}^2\rangle \geq \frac{1}{4}\langle[\hat{X}, \hat{Y}]\rangle^2$$

$$\Rightarrow \Delta A \cdot \Delta B \geq \frac{1}{2}|\langle[\hat{A}, \hat{B}]\rangle|$$

**注意：** 对任意力学量 $A$、$B$，任意量子态 $|\psi\rangle$，若 $A$ 与 $B$ 不对易即 $[\hat{A}, \hat{B}] \neq 0$，则 $\Delta A$ 和 $\Delta B$ 不能同时为零，也即 $A$ 与 $B$ 不能同时测定。

## 共同本征函数

设 $\hat{A}\psi_a = A_a \psi_a$，$\hat{B}\psi_b = B_b \psi_b$。若 $[\hat{A}, \hat{B}] \neq 0$，则 $\psi_a$ 不是 $\hat{B}$ 的本征函数，$\psi_b$ 不是 $\hat{A}$ 的本征函数。

若 $[\hat{A}, \hat{B}] = 0$，则可能存在 $\psi$，使 $\hat{A}\psi = A\psi$，$\hat{B}\psi = B\psi$，此时称 $\psi$ 为 $A$ 和 $B$ 的共同本征函数。

**定理：** 设 $\hat{A}|k\rangle = a_k |k\rangle$，另有 $\hat{B}$，若 $[\hat{A}, \hat{B}] = 0$，且 $a_k$ 不简并（即 $a_k$ 只对应一个本征态 $|k\rangle$），则 $|k\rangle$ 也是 $\hat{B}$ 的本征态，即 $A$ 和 $B$ 拥有共同本征态。

**证明：** $[\hat{A}, \hat{B}] = 0 \Rightarrow \hat{A}\hat{B} = \hat{B}\hat{A}$，$\hat{B}\hat{A}|k\rangle = \hat{B} \cdot a_k |k\rangle = a_k \hat{B}|k\rangle$。则 $\hat{A}(\hat{B}|k\rangle) = a_k(\hat{B}|k\rangle)$，$\therefore \hat{B}|k\rangle$ 也是 $A$ 属于本征值 $a_k$ 的本征态，故 $\hat{B}|k\rangle$ 与 $|k\rangle$ 是同一个量子态，即 $\hat{B}|k\rangle = b_k |k\rangle$。$A$、$B$ 拥有共同本征态 $|k\rangle$。

**例：** $\psi(\vec{r}) = \frac{1}{(2\pi\hbar)^{3/2}} e^{i\vec{p}\cdot\vec{r}/\hbar}$ 为 $\hat{p}_x$、$\hat{p}_y$、$\hat{p}_z$ 的共同本征函数，本征值为 $p_x$、$p_y$、$p_z$。

## 厄米算符本征值与本征态的特性

**转置算符：** 对任意 $\psi$ 和 $\varphi$，若 $\langle\psi|\hat{A}|\varphi\rangle = \langle\varphi|\hat{A}|\psi\rangle^*$，则称 $\hat{A}$ 和 $\hat{A}^T$ 互为彼此的转置算符。

**共轭算符：** 对算符 $\hat{A}$ 的每一元素取复共轭，得到 $\hat{A}^*$ 为 $\hat{A}$ 的共轭算符。

**厄米算符：** $\hat{A} = \hat{A}^\dagger = (\hat{A}^*)^T$，则称 $\hat{A}$ 为厄米算符。

**定理：** 厄米算符 $\hat{A}$ 在任意量子态下的平均值 $\bar{A}$ 为实数，$\hat{A}^\dagger$ 的平均值 $\overline{A^\dagger} \geq 0$。

**证明：** $\langle\psi|\hat{A}|\psi\rangle = \langle\psi|\hat{A}^\dagger|\psi\rangle = \langle\psi|\hat{A}|\psi\rangle^* = \langle\psi|\hat{A}|\psi\rangle$，$\therefore \bar{A} = \bar{A}^*$，$\bar{A}$ 为实数。

或：$\langle\psi|\hat{A}^\dagger|\psi\rangle = \langle\hat{A}\psi|\psi\rangle$，$\langle\psi|\hat{A}|\psi\rangle = \langle\hat{A}^\dagger\psi|\psi\rangle$，$\bar{A} = \bar{A}^*$，$\bar{A}$ 为实数。

$$\langle\psi|\hat{A}^2|\psi\rangle = \langle\psi|\hat{A}\hat{A}|\psi\rangle = \langle\psi|\hat{A}^\dagger\hat{A}|\psi\rangle = \langle\hat{A}\psi|\hat{A}\psi\rangle = \langle\phi|\phi\rangle \geq 0, \quad |\phi\rangle = \hat{A}|\psi\rangle$$

$\therefore \overline{A^2} \geq 0$。

### 厄米算符本征值的实数性

$$\hat{F}|k\rangle = \lambda_k |k\rangle$$

则 $\langle k|\hat{F}|k\rangle = \bar{F} = \langle k|\lambda_k |k\rangle = \lambda_k \langle k|k\rangle = \lambda_k$，$\therefore \lambda_k = \bar{F}$ 为实数（$\langle k|k\rangle = 1$）。

### 厄米算符本征态的正交性与完备性、封闭性

**① 厄米算符属于不同本征值的本征态必然正交**（对不同 $|k\rangle$ 可能有不同的 $\lambda$）

$$\hat{F}|k\rangle = \lambda_k |k\rangle, \quad \hat{F}|k'\rangle = \lambda_{k'} |k'\rangle$$

$$\langle k'|\hat{F}|k\rangle = \lambda_k \langle k'|k\rangle, \quad \langle k'|\hat{F}|k\rangle = \langle k'|\hat{F}^\dagger|k\rangle = \langle \hat{F}k'|k\rangle = \lambda_{k'} \langle k'|k\rangle$$

又 $\lambda_k$ 为实数，$\therefore \lambda_k = \lambda_k^*$，$\langle k'|\hat{F}|k\rangle = \lambda_k \langle k'|k\rangle = \lambda_{k'} \langle k'|k\rangle$，而 $\lambda_k \neq \lambda_{k'}$，$\therefore \langle k'|k\rangle = 0$，即 $|k\rangle$ 与 $|k'\rangle$ 正交。

**② 本征态的完备性**

$\hat{P}_k = |k\rangle\langle k|$ 为投影算符，$\hat{P}_k = \hat{P}_k^\dagger$。

若对任意 $|\psi\rangle$，有 $\hat{P}_k|\psi\rangle = \sum_k |k\rangle\langle k|\psi\rangle = |\psi\rangle$，则称基矢 $|k\rangle$ 具有完备性（任意 $|\psi\rangle$ 可按 $|k\rangle$ 展开）。

记 $c_k = \langle k|\psi\rangle$，则 $|\psi\rangle = \sum_k |k\rangle\langle k|\psi\rangle = \sum_k c_k |k\rangle$，$c_k$ 为用 $|k\rangle$ 将 $|\psi\rangle$ 做展开时的展开系数。

**定理：** 哈密顿算符 $\hat{H}$ 为厄米算符，满足本征方程 $\hat{H}|k\rangle = E_k |k\rangle$。对体系的任一归一化态 $\psi$，若 $\bar{H} = \langle\psi|\hat{H}|\psi\rangle$ 有下界（总大于某常数）但无上界，则 $\hat{H}$ 的本征态 $|k\rangle$ 的集合构成体系的一个完备集，即体系的任一量子态 $|\psi\rangle$ 可用 $|k\rangle$ 来展开。

$$\Rightarrow A_n = \sqrt{\frac{2}{a}\left[1 + \sin^2(k_n a)\right]}, \quad \psi_n(x) = A_n \sin(k_n x), \quad 0 < x < a; \quad 0, \quad x < 0$$

$$B_n = \sqrt{\frac{2}{a}\left[1 - \sin(2k_n a) + \sin^2(k_n a)\right]}, \quad \psi_n(x) = B_n e^{ik_n x}, \quad x > a$$

一个 $E_n$ 对应一个 $\psi_n$。

## 一维谐振子

$$V(x) = \frac{1}{2}kx^2 = \frac{1}{2}\mu\omega^2 x^2 \quad (-kx = m\ddot{x}, \quad \ddot{x} + \omega^2 x = 0, \quad \omega^2 = \frac{k}{\mu})$$

薛定谔方程：

$$\left[-\frac{\hbar^2}{2\mu}\frac{d^2}{dx^2} + \frac{1}{2}\mu\omega^2 x^2\right]\psi(x) = E\psi(x)$$

令 $\alpha = \sqrt{\frac{\mu\omega}{\hbar}}$，$\xi = \alpha x$，$\psi(x) = \varphi(\xi) = \left(\frac{\alpha}{\sqrt{\pi}}\right)^{1/2} \varphi(\xi)$，于是：

$$\left[-\frac{d^2}{d\xi^2} + \xi^2\right]\varphi(\xi) = \frac{2E}{\hbar\omega}\varphi(\xi)$$

$$-\frac{d^2\varphi(\xi)}{d\xi^2} + (\lambda - \xi^2)\varphi(\xi) = 0$$

为“消除”$\xi^2$ 项，试探设 $\varphi(\xi) = e^{-\xi^2/2}H(\xi)$：

$$\Rightarrow \frac{d^2H}{d\xi^2} - 2\xi\frac{dH}{d\xi} + (\lambda - 1)H(\xi) = 0$$

$\varphi(\xi) \to 0$，仅当 $\lambda = 2n + 1$ 时，$H_n(\xi)$ 有 $\varphi(\xi) \to 0$ 解，$H(\xi) = H_n(\xi) = (-1)^n e^{\xi^2}\frac{d^n}{d\xi^n}e^{-\xi^2}$。

$$\int_{-\infty}^{\infty} H_n(\xi)H_m(\xi)e^{-\xi^2}d\xi = \sqrt{\pi}2^n n! \delta_{nm}$$

$$\varphi_n(\xi) = N_n e^{-\xi^2/2}H_n(\xi), \quad N_n^2 \int e^{-\xi^2}H_n(\xi)H_n(\xi)d\xi = 1, \quad N_n = \sqrt{\frac{\alpha}{\sqrt{\pi}2^n n!}}$$

**能量分立化：**

$$E_n = \hbar\omega\left(n + \frac{1}{2}\right) = \left(n + \frac{1}{2}\right)\hbar\omega$$

$$\psi_n(x) = N_n e^{-\alpha^2 x^2/2} H_n(\alpha x)$$

### 补充：方程 $\frac{d^2H(\xi)}{d\xi^2} - 2\xi\frac{dH(\xi)}{d\xi} + (\lambda - 1)H(\xi) = 0$ 的两种解法

**① 幂级数解法，构造递推的系数关系**

$$H(\xi) = \sum_j a_j \xi^j, \quad [j(j-1) - 2j + (\lambda - 1)]a_j = 0, \quad (j+2)(j+1)a_{j+2} - (2j + 1 - \lambda)a_j = 0$$

$$\Rightarrow a_{j+2} = \frac{2j + 1 - \lambda}{(j+2)(j+1)}a_j$$

$\varphi(\xi)$ 按 $e^{\xi^2}$ 量级增长，不可积。级数存在（只有）有限项：$a_n \neq 0$，$a_{n+2} = 0$，即 $\lambda = 2n + 1$。

从而有 $a_{j+2} = \frac{2(j - n)}{(j+2)(j+1)}a_j$，多项式 $H(\xi)$ 只能含奇数项或偶数项，系数由高次项推至低次项。

方程可变化为：

$$\frac{d^2H_n}{d\xi^2} - 2\xi\frac{dH_n}{d\xi} + 2nH_n(\xi) = 0$$

其解为厄米多项式 $H_n(\xi)$。

$$H_n(\xi) = \sum_{k=0}^{\lfloor n/2 \rfloor} \frac{(-1)^k n!}{k!(n-2k)!}(2\xi)^{n-2k} \quad (\text{可通过递推 + 母函数求解})$$

$H_n(\xi)$ 满足：

$$H_n''(\xi) - 2\xi H_n'(\xi) + 2nH_n(\xi) = 0$$

母函数：

$$w(t, x) = e^{2xt - t^2}, \quad \frac{\partial w(t, x)}{\partial t} + 2(t - x)w(t, x) = 0$$

### 本征态的封闭性

$\hat{I}$ 为单位算符，$\hat{I}|\psi\rangle = |\psi\rangle$。

若本征态或基矢 $|k\rangle$ 满足 $\sum_k |k\rangle\langle k| = \hat{I}$，称为本征态或基矢 $|k\rangle$ 的封闭性；$\sum_k \hat{P}_k = \sum_k |k\rangle\langle k| = \hat{I}$ 称为投影算符的封闭性。

**完备性 & 封闭性：** 强调重点不同，完备性指任意 $|\psi\rangle$ 可按 $\{|k\rangle\}$ 展开，封闭性指数学上封闭性方程 $\sum_k |k\rangle\langle k| = \hat{I}$ 成立，两者相互依存。

**例：** 设体系的能量本征方程为 $\hat{H}|k\rangle = E_k |k\rangle$，证明哈密顿算符可表示为 $\hat{H} = \sum_k E_k |k\rangle\langle k|$（本征态具有完备性、封闭性）。

**证明：** $\hat{H}\sum_k |k\rangle\langle k| = \sum_k E_k |k\rangle\langle k|$，则 $\hat{H} = \hat{H}\sum_k |k\rangle\langle k| = \sum_k E_k |k\rangle\langle k|$，从而有 $\hat{H} = \sum_k E_k |k\rangle\langle k|$。

## 守恒量与能级简并度

### 力学量平均值的时间依赖特性

$$\bar{A}(t) = \langle\psi(t)|\hat{A}|\psi(t)\rangle$$

薛定谔方程：$i\hbar\frac{\partial}{\partial t}|\psi(t)\rangle = \hat{H}|\psi(t)\rangle$。在左矢空间中：$-i\hbar\frac{\partial}{\partial t}\langle\psi| = \langle\psi|\hat{H}$（$\hat{H} = \hat{H}^\dagger$）。

$$\frac{d\bar{A}}{dt} = \frac{\partial}{\partial t}\langle\psi|\hat{A}|\psi\rangle + \langle\psi|\frac{\partial\hat{A}}{\partial t}|\psi\rangle + \langle\psi|\hat{A}\frac{\partial}{\partial t}|\psi\rangle = -\frac{1}{i\hbar}\langle\psi|\hat{H}\hat{A}|\psi\rangle + \langle\psi|\frac{\partial\hat{A}}{\partial t}|\psi\rangle + \frac{1}{i\hbar}\langle\psi|\hat{A}\hat{H}|\psi\rangle$$

$$= \frac{1}{i\hbar}\langle\psi|[\hat{A}, \hat{H}]|\psi\rangle + \langle\psi|\frac{\partial\hat{A}}{\partial t}|\psi\rangle$$

若 $\frac{\partial\hat{A}}{\partial t} = 0$（$\hat{A}$ 不显含 $t$）且 $[\hat{A}, \hat{H}] = 0$，则 $\frac{d\bar{A}}{dt} = 0$，$\bar{A}$ 与时间无关，$A$ 在任何态 $\psi(t)$ 下的平均值 $\bar{A}$ 都不随时间改变。

### 守恒量

$A$ 在任何态 $\psi(t)$ 下的平均值 $\bar{A}$ 都不随 $t$ 改变，则称此时 $A$ 对应的力学量为体系的一个守恒量。

$$\frac{\partial\hat{A}}{\partial t} = 0 \text{ 且 } [\hat{A}, \hat{H}] = 0 \Rightarrow A \text{ 为守恒量}$$

**定理：** 若 $[\hat{F}, \hat{H}] = 0$，$[\hat{G}, \hat{H}] = 0$，但 $[\hat{F}, \hat{G}] \neq 0$，则体系的能级是简并的。（$F$、$G$ 为守恒量）

**证明：** $\hat{H}$ 有共同本征函数 $\psi$，$\hat{F}\psi = F\psi$，$\hat{H}\psi = E\psi$。$\because [\hat{G}, \hat{H}] = 0$，则 $\hat{H}(\hat{G}\psi) = \hat{G}\hat{H}\psi = E(\hat{G}\psi)$，即 $\hat{G}\psi$ 也是 $H$ 的本征态。又 $\hat{F}(\hat{G}\psi) \neq F(\hat{G}\psi)$，则 $\hat{G}\psi$ 不是 $\hat{F}$ 的本征态，$\therefore \hat{G}\psi$ 和 $\psi$ 不是一个态，即 $E$ 对应至少两个态，能级简并。

# 表象变换与矩阵力学

设 $\hat{F} = (\hat{A}_1, \hat{A}_2, \ldots, \hat{A}_n)$ 是一组力学量完全集，$|k\rangle$ 是其共同本征态，其中 $k$ 表征所有量子数。

$|k\rangle$ 是正交归一的，满足 $\langle k|m\rangle = \delta_{km} = \begin{cases} 1, & k = m \\ 0, & k \neq m \end{cases}$，$|k\rangle$ 是完备的，即体系中任一量子态可按 $|k\rangle$ 展开。

$\{|k\rangle\}$ 构成一个表象，可称为 $F$ 表象，$F$ 构成无穷维的希尔伯特空间，量子态是希尔伯特空间中的一个矢量，$|\psi\rangle = \sum_k a_k |k\rangle$，则 $a_k = \langle k|\psi\rangle$ 为内积，也可视为投影。

## 表象间的转化

$F$ 表象中，$|k\rangle = \psi_k$，$|\psi\rangle = \sum_k a_k |k\rangle$，$\psi$ 在 $F$ 表象中可用系数列向量表示为 $a = \begin{pmatrix} a_1 \\ a_2 \\ \vdots \\ a_k \end{pmatrix}$。

$a'$ 与 $a$ 的转化实际上是基矢之间的转化。

$$|\psi\rangle = \sum_k a_k |k\rangle = \sum_\beta a'_\beta |\beta\rangle$$

$|k\rangle = \sum_\beta \langle\beta|k\rangle \cdot |\beta\rangle$（$|k\rangle$ 按 $|\beta\rangle$ 展开），从而统一基矢为 $|\beta\rangle$。

则 $a'_\beta = \sum_k a_k \langle\beta|k\rangle$，即 $a' = S a$，记 $S_{\beta k} = \langle\beta|k\rangle$，$S = \begin{pmatrix} S_{11} & S_{12} & \cdots & S_{1k} \\ S_{21} & S_{22} & \cdots & S_{2k} \\ \vdots & \vdots & \ddots & \vdots \\ S_{\beta 1} & S_{\beta 2} & \cdots & S_{\beta k} \end{pmatrix}$。

**注：** $a$、$a'$ 均为系数列向量，与本征态形式相似但意义完全不同。$|k\rangle$ 在希尔伯特空间中可表示为一个列向量，$|\psi\rangle$ 按 $|k\rangle$ 展开所得系数列为 $a$。

从矢量的角度考虑，$|\psi\rangle = (e_1, e_2, \ldots, e_k)\begin{pmatrix} a_1 \\ a_2 \\ \vdots \\ a_k \end{pmatrix}$，即列向量 $e_k$ 的线性组合。

要消去 $(e_1', e_2', \ldots, e_k')$，则 $(e_1', e_2', \ldots, e_k') = (e_1, e_2, \ldots, e_k)S$，其中 $S = \begin{pmatrix} S_{11} & S_{12} & \cdots & S_{1k} \\ S_{21} & S_{22} & \cdots & S_{2k} \\ \vdots & \vdots & \ddots & \vdots \\ S_{k1} & S_{k2} & \cdots & S_{kk} \end{pmatrix}$，系数列向量 $a' = S a$。

$$\langle k'|k\rangle = \delta_{k'k}, \quad \langle k|k\rangle = 1$$

$$|k\rangle = \sum_\beta S_{\beta k}|\beta\rangle, \quad \langle k'|k\rangle = \left(\sum_\beta S_{\beta k'}^*\langle\beta|\right)\left(\sum_{\beta'} S_{\beta' k}|\beta'\rangle\right) = \sum_\beta S_{\beta k'}^* S_{\beta k} = \delta_{k'k}$$

$$\langle m|k\rangle = \left(\sum_\beta S_{\beta m}^*\langle\beta|\right)\left(\sum_{\beta'} S_{\beta' k}|\beta'\rangle\right) = \sum_\beta S_{\beta m}^* S_{\beta k} = \delta_{mk}$$

$$\Rightarrow S^\dagger S = S S^\dagger = \begin{pmatrix} 1 & 0 & \cdots & 0 \\ 0 & 1 & \cdots & 0 \\ \vdots & \vdots & \ddots & \vdots \\ 0 & 0 & \cdots & 1 \end{pmatrix} = I$$

$S$ 为幺正矩阵。

$$(e_1', e_2', \ldots, e_k') = (e_1, e_2, \ldots, e_k)S$$

$$(e_1', e_2', \ldots, e_k') = (e_1, e_2, \ldots, e_k)\begin{pmatrix} \langle e_1|e_1'\rangle & \langle e_1|e_2'\rangle & \cdots & \langle e_1|e_k'\rangle \\ \langle e_2|e_1'\rangle & \langle e_2|e_2'\rangle & \cdots & \langle e_2|e_k'\rangle \\ \vdots & \vdots & \ddots & \vdots \\ \langle e_k|e_1'\rangle & \langle e_k|e_2'\rangle & \cdots & \langle e_k|e_k'\rangle \end{pmatrix}$$

$$= (e_1, e_2, \ldots, e_k)S^\dagger$$

## 球坐标下的薛定谔方程与氢原子

$$\left[-\frac{\hbar^2}{2\mu}\nabla^2 + V(r)\right]\psi = E\psi$$

在球坐标中：

$$\nabla^2 = \frac{1}{r^2}\frac{\partial}{\partial r}\left(r^2\frac{\partial}{\partial r}\right) + \frac{1}{r^2\sin\theta}\frac{\partial}{\partial\theta}\left(\sin\theta\frac{\partial}{\partial\theta}\right) + \frac{1}{r^2\sin^2\theta}\frac{\partial^2}{\partial\varphi^2}$$

设 $\psi(r, \theta, \varphi) = R(r)Y(\theta, \varphi)$，代入得：

$$\frac{1}{R}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) + \frac{2\mu r^2}{\hbar^2}[E - V(r)] = -\frac{1}{Y}\left[\frac{1}{\sin\theta}\frac{\partial}{\partial\theta}\left(\sin\theta\frac{\partial Y}{\partial\theta}\right) + \frac{1}{\sin^2\theta}\frac{\partial^2 Y}{\partial\varphi^2}\right] = \lambda$$

**径向方程：**

$$\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) + \left[\frac{2\mu}{\hbar^2}(E - V(r)) - \frac{\lambda}{r^2}\right]R(r) = 0$$

**角向方程：**

$$\frac{1}{\sin\theta}\frac{\partial}{\partial\theta}\left(\sin\theta\frac{\partial Y}{\partial\theta}\right) + \frac{1}{\sin^2\theta}\frac{\partial^2 Y}{\partial\varphi^2} + \lambda Y = 0$$

**① 考虑角向方程** $Y(\theta, \varphi) = \Theta(\theta)\Phi(\varphi)$：

$$\frac{\sin\theta}{\Theta}\frac{d}{d\theta}\left(\sin\theta\frac{d\Theta}{d\theta}\right) + \lambda\sin^2\theta = -\frac{1}{\Phi}\frac{d^2\Phi}{d\varphi^2} = m^2$$

$$\frac{d^2\Phi}{d\varphi^2} + m^2\Phi(\varphi) = 0 \Rightarrow \Phi_m(\varphi) = \frac{1}{\sqrt{2\pi}}e^{im\varphi}$$

对于勒让德方程 $\frac{1}{\sin\theta}\frac{d}{d\theta}\left(\sin\theta\frac{d\Theta}{d\theta}\right) + \left(\lambda - \frac{m^2}{\sin^2\theta}\right)\Theta(\theta) = 0$，为使 $\Theta(\theta)$ 在区间 $[0, \pi]$ 有限，$\lambda$ 只能取 $\lambda = l(l+1)$。

$|m| \leq l$ 时才有 $\Theta(\theta) \neq 0$，$\Rightarrow m = 0, \pm 1, \ldots, \pm l$。

$$\Theta_{lm}(\theta) = N_{lm}P_l^m(\cos\theta), \quad N_{lm} = \sqrt{\frac{(2l+1)(l-|m|)!}{2(l+|m|)!}}$$

$$Y_{lm}(\theta, \varphi) = N_{lm}P_l^m(\cos\theta)\Phi_m(\varphi) = N_{lm}\sqrt{\frac{(2l+1)(l-|m|)!}{4\pi(l+|m|)!}}P_l^m(\cos\theta)e^{im\varphi}$$

球谐函数满足正交关系：

$$\int_0^{2\pi}\int_0^\pi Y_{lm}^*(\theta, \varphi)Y_{l'm'}(\theta, \varphi)\sin\theta d\theta d\varphi = \delta_{ll'}\delta_{mm'}$$

$Y_{lm}$ 是 $\hat{l}^2$ 和 $\hat{l}_z$ 的共同本征函数。

## 氢原子

**径向方程：**

$$\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) + \left[\frac{2\mu}{\hbar^2}\left(E - V(r)\right) - \frac{l(l+1)}{r^2}\right]R(r) = 0$$

$$V(r) = -\frac{e^2}{4\pi\varepsilon_0 r}, \quad \kappa = \sqrt{\frac{-2\mu E}{\hbar^2}}$$

则方程为：

$$\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) + \left[\frac{2\mu}{\hbar^2}\left(E + \frac{e^2}{4\pi\varepsilon_0 r}\right) - \frac{l(l+1)}{r^2}\right]R(r) = 0$$

引入约化径向波函数 $u(r) = rR_l(r)$，则 $u(r)$ 满足：

$$\frac{d^2u}{dr^2} + \left[\frac{2\mu}{\hbar^2}\left(E + \frac{e^2}{4\pi\varepsilon_0 r}\right) - \frac{l(l+1)}{r^2}\right]u(r) = 0$$

$\because V(r) < 0$，$R_l(r) \to 0$，$r \to \infty$ 时薛定谔方程约为 $\frac{d^2u}{dr^2} + \frac{2\mu E}{\hbar^2}u = 0$，若 $E > 0$，$u(r)$ 呈振荡形式，不满足束缚态，则 $E < 0$。从能量角度分析，$E = V + K$，$K < |V|$，$E < 0$。核与电子“双星模型”。

于是方程化为：

$$\frac{d^2u}{d\rho^2} + \left[\frac{\beta}{\rho} - \frac{1}{4} - \frac{l(l+1)}{\rho^2}\right]u(\rho) = 0$$

其中 $\rho = 2\kappa r$，$\beta = \frac{\mu e^2}{4\pi\varepsilon_0\hbar^2\kappa}$。

$\rho \to \infty$ 时，方程近似为 $\frac{d^2u}{d\rho^2} - \frac{1}{4}u(\rho) = 0$，$u(\rho) \sim e^{-\rho/2}$。

$\rho \to 0$ 时，方程近似为 $\frac{d^2u}{d\rho^2} - \frac{l(l+1)}{\rho^2}u(\rho) = 0$，$u(\rho) \sim \rho^{l+1}$。

利用渐进解，设 $u(\rho) = \rho^{l+1}e^{-\rho/2}v(\rho)$。

$v(\rho)$ 满足方程：

$$\rho\frac{d^2v}{d\rho^2} + (2l + 2 - \rho)\frac{dv}{d\rho} + [\beta - l - 1]v(\rho) = 0$$

为合流超几何方程。

$v(\rho)$ 有多项式解的条件是 $\beta - l - 1 = n_r$，$\beta = l + 1 + n_r$（$n_r = 0, 1, 2, \ldots$）。$n = l + 1 + n_r$，$n = 1, 2, 3, \ldots$。

$$\kappa = \frac{\mu e^2}{4\pi\varepsilon_0\hbar^2 n} \Rightarrow E_n = -\frac{\mu e^4}{32\pi^2\varepsilon_0^2\hbar^2 n^2} = -\frac{13.6\text{ eV}}{n^2}$$

$l$ 的取值为 $0, 1, \ldots, n-1$；$m$ 的取值为 $-l, -(l-1), \ldots, 0, \ldots, l$。能量本征态由 $(n, l, m)$ 表征。

**氢原子轨道角动量的取值：**

$$\hat{l}^2\psi_{nlm} = l(l+1)\hbar^2\psi_{nlm}, \quad l = 0, 1, \ldots, n-1$$

**氢原子轨道角动量 $z$ 方向的取值：**

$$\hat{l}_z\psi_{nlm} = m\hbar\psi_{nlm}, \quad \hat{l}_z Y_{lm} = m\hbar Y_{lm}$$

$$R_{nl}(r) = N_{nl}\rho^l e^{-\rho/2}L_{n+l}^{2l+1}(\rho), \quad N_{nl} = \sqrt{\left(\frac{2}{na_0}\right)^3\frac{(n-l-1)!}{2n[(n+l)!]^3}}$$

**归一化条件：**

$$\int_0^\infty |R_{nl}(r)|^2 r^2 dr = 1, \quad \int |\psi_{nlm}|^2 r^2 \sin\theta dr d\theta d\varphi = 1$$

**能级简并：** $n = n_r + l + 1$，能级简并度 $\sum_{l=0}^{n-1}(2l+1) = n^2$。

**径向位置概率分布：** $(r, r+dr)$ 内概率为 $r^2 dr \int |\psi_{nlm}(r, \theta, \varphi)|^2 \sin\theta d\theta d\varphi = r^2 |R_{nl}(r)|^2 dr = |u_{nl}(r)|^2 dr$。