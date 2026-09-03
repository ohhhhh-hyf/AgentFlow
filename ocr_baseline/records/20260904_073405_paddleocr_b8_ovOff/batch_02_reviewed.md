# 科技

华中科技大学

Y OF SCIENCE AND TECHNOLOGY HUAZHONG UNIVERSITY OF SCIENCE AND TECHNOLOGY

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

由 $\hat{l}_z |lm\rangle = m\hbar |lm\rangle$，$m$ 为实数，则 $\langle lm|\hat{l}_z = m\hbar \langle lm|$，故

$$\bar{l}_x = \frac{1}{i\hbar}[m\hbar \langle lm|\hat{l}_y|lm\rangle - m\hbar \langle lm|\hat{l}_y|lm\rangle] = 0$$

$$\therefore \bar{l}_x = 0$$

**例2.** $|lm\rangle$ 为 $\hat{l}^2$、$\hat{l}_z$ 的共同本征态，求 $\overline{l_x^2}$、$\overline{l_y^2}$。

$$\overline{l_x^2} = \langle lm|\hat{l}_x^2|lm\rangle = \langle lm|(\hat{l}^2 - \hat{l}_z^2)|lm\rangle = [l(l+1) - m^2]\hbar^2$$

$$\overline{l_y^2} = \langle lm|\hat{l}_y^2|lm\rangle = \langle lm|(\hat{l}^2 - \hat{l}_z^2)|lm\rangle = [l(l+1) - m^2]\hbar^2$$

由 $\hat{l}_x^2 = \hat{l}^2 - \hat{l}_z^2 - \hat{l}_y^2$，$\hat{l}_y^2 = \hat{l}^2 - \hat{l}_z^2 - \hat{l}_x^2$，利用对易关系：

$$\hat{l}_y \hat{l}_z \hat{l}_x - \hat{l}_z \hat{l}_x \hat{l}_y = (\hat{l}_y \hat{l}_z - \hat{l}_z \hat{l}_y)\hat{l}_x + \hat{l}_z(\hat{l}_y \hat{l}_x - \hat{l}_x \hat{l}_y) = [\hat{l}_y, \hat{l}_z]\hat{l}_x + \hat{l}_z[\hat{l}_y, \hat{l}_x]$$

$$= i\hbar \hat{l}_x^2 + \hat{l}_z(-i\hbar \hat{l}_y) = i\hbar(\hat{l}_x^2 - \hat{l}_z \hat{l}_y)$$

$$\overline{l_x^2} = \frac{1}{2}[\langle lm|\hat{l}^2|lm\rangle - \langle lm|\hat{l}_z^2|lm\rangle] = \frac{1}{2}[l(l+1) - m^2]\hbar^2$$

设 $\overline{l_x^2} = \overline{l_y^2} = \frac{1}{2}[l(l+1) - m^2]\hbar^2$

**方法：** 将本征态对应的算符尽量转化到最左/右边，直接作用到态矢上。

# 不确定度关系的严格证明

任意给定力学量 $A$ 和 $B$，对应的米算符为 $\hat{A}$ 和 $\hat{B}$，分别具有不确定度 $\Delta A$ 和 $\Delta B$，则有以下关系：

$$\Delta A \Delta B \ge \frac{1}{2}|\langle[\hat{A},\hat{B}]\rangle|$$

其中 $\langle[\hat{A},\hat{B}]\rangle = \langle \hat{A}\hat{B} - \hat{B}\hat{A} \rangle$ 对成立，$\Delta A = \sqrt{\langle(\hat{A}-\langle A\rangle)^2\rangle}$，$\Delta B = \sqrt{\langle(\hat{B}-\langle B\rangle)^2\rangle}$。

也即：

$$[\hat{A},\hat{B}] = [\Delta\hat{A}+\langle A\rangle, \Delta\hat{B}+\langle B\rangle] = (\Delta\hat{A}+\langle A\rangle)(\Delta\hat{B}+\langle B\rangle) - (\Delta\hat{B}+\langle B\rangle)(\Delta\hat{A}+\langle A\rangle) = [\Delta\hat{A}, \Delta\hat{B}]$$

$$\Delta A = \sqrt{\langle \hat{A}^2 \rangle - \langle A\rangle^2} = \sqrt{\langle(\hat{A}-\langle A\rangle)^2\rangle}, \quad \Delta B = \sqrt{\langle \hat{B}^2 \rangle - \langle B\rangle^2}$$

要证也即：

$$\langle(\hat{A}-\langle A\rangle)^2\rangle\langle(\hat{B}-\langle B\rangle)^2\rangle \ge \frac{1}{4}|\langle[\hat{A}-\langle A\rangle, \hat{B}-\langle B\rangle]\rangle|^2$$

令 $x = \hat{A}-\langle A\rangle$，$r = \hat{B}-\langle B\rangle$，要证变为：

$$\langle x^2\rangle\langle r^2\rangle \ge \frac{1}{4}|\langle[x,r]\rangle|^2$$

联想 $b^2 \ge 4ac$。

考虑 $|\phi\rangle = (\lambda \hat{A} + i\hat{B})|\psi\rangle$，$\langle\phi|\phi\rangle \ge 0$：

$$\langle(\lambda\hat{A}+i\hat{B})\psi|(\lambda\hat{A}+i\hat{B})\psi\rangle = (\lambda\langle\psi|\hat{A} - i\langle\psi|\hat{B})(\lambda\hat{A}|\psi\rangle + i\hat{B}|\psi\rangle)$$

$\hat{A}, \hat{B}$ 为厄米算符：

$$= (\lambda\langle\psi|\hat{A} - i\langle\psi|\hat{B})(\lambda\hat{A}|\psi\rangle + i\hat{B}|\psi\rangle)$$

$$= \lambda^2\langle\psi|\hat{A}^2|\psi\rangle + \langle\psi|\hat{B}^2|\psi\rangle + i\lambda(\langle\psi|\hat{A}\hat{B}|\psi\rangle - \langle\psi|\hat{B}\hat{A}|\psi\rangle) = \lambda^2\langle\hat{A}^2\rangle + \langle\hat{B}^2\rangle + i\lambda\langle[\hat{A},\hat{B}]\rangle$$

$\because \forall \lambda$，$\langle\phi|\phi\rangle \ge 0$，$\therefore (\langle i[\hat{A},\hat{B}]\rangle)^2 \le 4\langle\hat{A}^2\rangle\langle\hat{B}^2\rangle$，即：

$$\langle\hat{A}^2\rangle\langle\hat{B}^2\rangle \ge \frac{1}{4}|\langle[\hat{A},\hat{B}]\rangle|^2$$

$$\therefore \Delta A \Delta B \ge \frac{1}{2}|\langle[\hat{A},\hat{B}]\rangle|$$

**结论**：对任意力学量 $A$、$B$，任意量子态 $|\psi\rangle$，若 $A$ 与 $B$ 不对易（即 $[\hat{A},\hat{B}] \neq 0$），则 $\Delta A$ 和 $\Delta B$ 不能同时为零，也即 **$A$ 与 $B$ 不能同时测定**。

## 共同本征函数

设 $\hat{A}\psi_a = A_a\psi_a$，$\hat{B}\psi_b = B_b\psi_b$。若 $[\hat{A},\hat{B}] \neq 0$，则 $\psi_a$ 不是 $\hat{B}$ 的本征函数，$\psi_b$ 不是 $\hat{A}$ 的本征函数。

若 $[\hat{A},\hat{B}] = 0$，则可能存在 $\psi$，使 $\hat{A}\psi = A\psi$，$\hat{B}\psi = B\psi$，此时称 $\psi$ 为 $A$ 和 $B$ 的**共同本征函数**。

### 定理

设 $\hat{A}|k\rangle = a_k|k\rangle$，另有 $\hat{B}$，若 $[\hat{A},\hat{B}] = 0$，且 $a_k$ 不简并（即 $a_k$ 只对应一个本征态 $|k\rangle$），则 $|k\rangle$ 也是 $\hat{B}$ 的本征态，即 $A$ 和 $B$ 拥有共同本征态。

**证明**：

$[\hat{A},\hat{B}] = 0 \Rightarrow \hat{A}\hat{B} = \hat{B}\hat{A}$。

$$\hat{B}\hat{A}|k\rangle = \hat{B} \cdot a_k|k\rangle = a_k \hat{B}|k\rangle$$

则 $\hat{A}(\hat{B}|k\rangle) = a_k(\hat{B}|k\rangle)$，$\therefore \hat{B}|k\rangle$ 也是 $A$ 属于本征值 $a_k$ 的本征态，故 $\hat{B}|k\rangle$ 与 $|k\rangle$ 是一个量子态，即 $\hat{B}|k\rangle = b_k|k\rangle$。$A$、$B$ 拥有共同本征态 $|k\rangle$。

### 例

$\psi(\vec{r}) = \frac{1}{(2\pi\hbar)^{3/2}} e^{i\vec{p}\cdot\vec{r}/\hbar}$ 为 $\hat{p}_x, \hat{p}_y, \hat{p}_z$ 的共同本征函数，本征值为 $p_x, p_y, p_z$。$\hat{p}\psi(\vec{r}) = \vec{p}\psi(\vec{r})$。

## 厄米算符本征值与本征态的特性

### 转置算符、共轭算符与厄米算符

**转置算符**：对 $\hat{A}$ 和 $\hat{\varphi}$，若 $\langle \psi | \hat{A} | \varphi \rangle = \langle \varphi | \hat{A}^T | \psi \rangle$，则称 $\hat{A}$ 和 $\hat{A}^T$ 互为彼此的转置算符。

**共轭算符**：对算符 $\hat{A}$ 的每一矩阵元取复共轭，得到 $\hat{A}^*$ 为 $\hat{A}$ 的转置算符。

**厄米算符**：若 $\hat{A} = \hat{A}^\dagger = \hat{A}^{*T}$，则称 $\hat{A}$ 为厄米算符。

**定理**：厄米算符 $\hat{A}$ 在任意量子态下的平均值 $\langle A \rangle$ 为实数，$\hat{A}^2$ 的平均值 $\langle A^2 \rangle \ge 0$。

证明：
$$\langle \psi | \hat{A} | \psi \rangle = \langle \psi | \hat{A}^\dagger | \psi \rangle = \langle \psi | \hat{A} | \psi \rangle^* = \langle \psi | \hat{A} | \psi \rangle$$
∴ $\hat{A} = \hat{A}^\dagger$，$\langle A \rangle$ 为实数。

即：$\langle \psi | \hat{A}^\dagger | \psi \rangle = \langle \hat{A} \psi | \psi \rangle$，$\langle \psi | \hat{A} | \psi \rangle = \langle \hat{A}^\dagger \psi | \psi \rangle$，$\hat{A} = \hat{A}^\dagger = \hat{A}^{*T}$，$\langle A \rangle$ 为实数。

$$\langle \psi | \hat{A}^2 | \psi \rangle = \langle \psi | \hat{A} \hat{A} | \psi \rangle = \langle \psi | \hat{A}^\dagger \hat{A} | \psi \rangle = \langle \hat{A} \psi | \hat{A} \psi \rangle = \langle \Phi | \Phi \rangle \ge 0$$
∴ $\langle A^2 \rangle \ge 0$，其中 $|\Phi\rangle = \hat{A}|\psi\rangle$。

### 厄米算符本征值的实数性

设 $\hat{F}|k\rangle = \lambda_k |k\rangle$，则
$$\langle k | \hat{F} | k \rangle = \langle k | \lambda_k | k \rangle = \lambda_k \langle k | k \rangle = \lambda_k$$
又 $\langle k | \hat{F} | k \rangle = \langle k | \hat{F}^\dagger | k \rangle = \langle k | \hat{F} | k \rangle^* = \lambda_k^*$，且 $\langle k | k \rangle = 1$，
∴ $\lambda_k = \lambda_k^*$，即 $\lambda_k$ 为实数。

### 厄米算符本征态的正交性与完备性、封闭性

**① 厄米算符属于不同本征值的本征态必然正交**（对不同 $|k\rangle$ 可能有不同的 $\lambda_k$）

设 $\hat{F}|k\rangle = \lambda_k |k\rangle$，$\hat{F}|k'\rangle = \lambda_{k'} |k'\rangle$。

$$\langle k' | \hat{F} | k \rangle = \lambda_k \langle k' | k \rangle$$
$$\langle k' | \hat{F} | k \rangle = \langle k' | \hat{F}^\dagger | k \rangle = \langle \hat{F} k' | k \rangle = \lambda_{k'} \langle k' | k \rangle$$

又 $\lambda_k$ 为实数，$\lambda_{k'} = \lambda_{k'}^*$，
$$\lambda_k \langle k' | k \rangle = \lambda_{k'} \langle k' | k \rangle$$
而 $\lambda_k \ne \lambda_{k'}$，故 $\langle k' | k \rangle = 0$，即 $|k\rangle$ 与 $|k'\rangle$ 正交。

**② 本征态的完备性**

$\hat{P}_k = |k\rangle\langle k|$ 为投影算符，$\hat{P}_k = \hat{P}_k^\dagger$。

若对任意 $|\psi\rangle$，有 $\hat{P}|\psi\rangle = \sum_k |k\rangle\langle k|\psi\rangle = |\psi\rangle$，则称基矢 $|k\rangle$ 具有完备性（任意 $|\psi\rangle$ 可按 $|k\rangle$ 展开）。

记 $C_k = \langle k|\psi\rangle$，则 $|\psi\rangle = \sum_k |k\rangle\langle k|\psi\rangle = \sum_k C_k |k\rangle$，$C_k$ 为用 $|k\rangle$ 将 $|\psi\rangle$ 做展开时的展开系数。

**定理**：哈密顿算符 $\hat{H}$ 为厄米算符，满足本征方程 $\hat{H}|k\rangle = E_k |k\rangle$。对体系的任一归一化态 $|\psi\rangle$，若 $\langle \hat{H} \rangle = \langle \psi|\hat{H}|\psi\rangle$ 有下界（总大于某常数）但无上界，则 $\hat{H}$ 的本征态 $|k\rangle$ 的集合构成体系的一个**完备集**，即体系的任一量子态 $|\psi\rangle$ 可用 $|k\rangle$ 来展开。

## 一维谐振子

上一页末尾为“中科技大学”，本页内容为量子力学中一维谐振子的求解，属于新章节，故另起标题。

### 束缚态波函数与能级

由边界条件可得：

$$A_n = 2\left[a + \frac{\sin(2k_n a)}{2k_n}\right]^{-1/2}, \quad \psi_n(x) = A_n \sin(k_n x), \quad 0 < x < a$$

$$B_n = \left[a - \frac{\sin(2k_n a)}{2k_n}\right]^{-1/2} \sin(k_n a), \quad \psi_n(x) = B_n e^{-k_n x}, \quad x > a$$

一个 $E_n$ 对应一个 $\psi_n$。

---

### 一维谐振子

势能：

$$V(x) = \frac{1}{2} k x^2 = \frac{1}{2} \mu \omega^2 x^2$$

由 $-kx = m\ddot{x}$，得 $\ddot{x} + \omega^2 x = 0$，其中 $\omega^2 = \frac{k}{\mu}$。

薛定谔方程：

$$\left[-\frac{\hbar^2}{2\mu} \frac{d^2}{dx^2} + \frac{1}{2} \mu \omega^2 x^2\right] \psi(x) = E \psi(x)$$

令 $\alpha = \sqrt{\frac{\mu \omega}{\hbar}}$，$s = \alpha x$，记 $\psi(x) = \phi(s)$，则方程化为：

$$\left[-\frac{d^2}{ds^2} + s^2\right] \phi(s) = \lambda \phi(s)$$

即：

$$\frac{d^2 \phi(s)}{ds^2} + (\lambda - s^2) \phi(s) = 0$$

为“消除”$s^2$ 项，试探设 $\phi(s) = e^{-s^2/2} H(s)$，代入得：

$$H''(s) - 2s H'(s) + (\lambda - 1) H(s) = 0$$

要求 $\phi(s) \to 0$（当 $|s| \to \infty$）。**仅当 $\lambda = 2n + 1$ 时，$H_n(s)$ 有 $\phi(s) \to 0$ 的解**，此时 $H(s) = H_n(s) = (-1)^n e^{s^2} \frac{d^n}{ds^n} e^{-s^2}$。

正交归一性：

$$\int_{-\infty}^{\infty} H_m(s) H_n(s) e^{-s^2} ds = \sqrt{\pi} \, 2^n n! \, \delta_{mn}$$

归一化波函数：

$$\phi_n(s) = N_n e^{-s^2/2} H_n(s), \quad N_n = \left(\sqrt{\pi} \, 2^n n!\right)^{-1/2}$$

$$\psi_n(x) = N_n e^{-\alpha^2 x^2 / 2} H_n(\alpha x)$$

**能量分立化**：

$$E_n = \hbar \omega \left(n + \frac{1}{2}\right) = \left(n + \frac{1}{2}\right) \hbar \omega, \quad n = 0, 1, 2, \dots$$

---

### 补充：方程 $H''(s) - 2s H'(s) + (\lambda - 1) H(s) = 0$ 的两种解法

#### ① 幂级数解法（构造递推的系数关系）

设 $H(s) = \sum_j a_j s^j$，代入方程得递推关系：

$$(j+2)(j+1) a_{j+2} - 2j a_j + (\lambda - 1) a_j = 0$$

即：

$$(j+2)(j+1) a_{j+2} = (2j + 1 - \lambda) a_j$$

若级数无穷，则 $\phi(s)$ 按 $e^{s^2}$ 量级增长，不可积。**级数必须只有有限项**，即存在 $n$ 使得 $a_n \neq 0$ 且 $a_{n+2} = 0$，由此得 $\lambda = 2n + 1$。

从而有 $a_{j+2} = \frac{2j + 1 - \lambda}{(j+2)(j+1)} a_j$，多项式 $H(s)$ 只能含奇数项或偶数项，系数由高次项推至低次项。

#### ② 厄米多项式解法

方程可化为：

$$H''(s) - 2s H'(s) + 2n H(s) = 0$$

其解为厄米多项式 $H_n(s)$：

$$H_n(s) = \sum_{k=0}^{\lfloor n/2 \rfloor} \frac{(-1)^k n!}{k! (n-2k)!} (2s)^{n-2k}$$

（可通过递推 + 母函数求解）

**厄米多项式性质**：

- 满足微分方程：$H_n''(s) - 2s H_n'(s) + 2n H_n(s) = 0$
- 母函数：$w(t, x) = e^{2tx - t^2}$，且 $\frac{\partial w}{\partial t} + 2(t - x) w(t, x) = 0$

### 本征态的封闭性

若本征态或基矢 $|k\rangle$ 满足 $\sum_k |k\rangle\langle k| = 1$，称为本征态或基矢 $|k\rangle$ 的**封闭性**；其中 $\hat{P}_k = |k\rangle\langle k|$ 称为投影算符，$\sum_k \hat{P}_k = 1$ 称为投影算符的封闭性。

**完备性与封闭性**：两者强调重点不同。完备性指任意 $|\psi\rangle$ 可按 $\{|k\rangle\}$ 展开；封闭性指数学上 $\sum_k |k\rangle\langle k| = \hat{I}$ 成立。两者相互依存。

**例**：设体系的能量本征方程为 $\hat{H}|k\rangle = E_k|k\rangle$，证明哈密顿算符可表示为 $\hat{H} = \sum_k E_k |k\rangle\langle k|$（本征态具有完备性、封闭性）。

证明：$\hat{H}\sum_k |k\rangle\langle k| = \sum_k E_k |k\rangle\langle k|$，则 $\hat{H}\sum_k |k\rangle\langle k| = \sum_k E_k |k\rangle\langle k|$，从而有 $\hat{H} = \sum_k E_k |k\rangle\langle k|$。

---

### 守恒量与能级简并度

#### 力学量平均值的时间依赖特性

$\bar{A}(t) = \langle\psi(t)|\hat{A}|\psi(t)\rangle$，薛定谔方程：$i\hbar\frac{\partial}{\partial t}|\psi(t)\rangle = \hat{H}|\psi(t)\rangle$。在左矢空间中：$-i\hbar\frac{\partial}{\partial t}\langle\psi| = \langle\psi|\hat{H}$（$\hbar = 1$）

$$\frac{d\bar{A}}{dt} = \frac{\partial}{\partial t}\langle\psi|\hat{A}|\psi\rangle + \langle\psi|\frac{\partial \hat{A}}{\partial t}|\psi\rangle + \langle\psi|\hat{A}\frac{\partial}{\partial t}|\psi\rangle = -i\langle\psi|\hat{H}\hat{A}|\psi\rangle + \langle\psi|\frac{\partial \hat{A}}{\partial t}|\psi\rangle + i\langle\psi|\hat{A}\hat{H}|\psi\rangle$$

$$= \langle\psi|[\hat{A}, \hat{H}]|\psi\rangle + \langle\psi|\frac{\partial \hat{A}}{\partial t}|\psi\rangle$$

若 $\frac{\partial \hat{A}}{\partial t} = 0$（$\hat{A}$ 不显含 $t$）且 $[\hat{A}, \hat{H}] = 0$，则 $\frac{d\bar{A}}{dt} = 0$，$\bar{A}$ 与时间无关。即 $\hat{A}$ 在任何态 $|\psi(t)\rangle$ 下的平均值 $\bar{A}$ 都不随时间改变。

#### 守恒量

若 $\hat{A}$ 在任何态 $|\psi(t)\rangle$ 下的平均值 $\bar{A}$ 都不随 $t$ 改变，则称此时 $\hat{A}$ 对应的力学量为体系的一个**守恒量**。

条件：$\frac{\partial \hat{A}}{\partial t} = 0$ 且 $[\hat{A}, \hat{H}] = 0$，则 $\hat{A}$ 为守恒量。

**定理**：若 $[\hat{F}, \hat{H}] = 0$，$[\hat{G}, \hat{H}] = 0$，但 $[\hat{F}, \hat{G}] \neq 0$，则体系的能级是简并的。（$\hat{F}$、$\hat{G}$ 为守恒量）

证明：设 $\hat{H}$ 有共同本征函数 $\psi$，$\hat{F}\psi = F\psi$，$\hat{H}\psi = E\psi$。∵ $[\hat{G}, \hat{H}] = 0$，则 $\hat{G}\hat{H}\psi = \hat{G}E\psi$，即 $\hat{H}(\hat{G}\psi) = E(\hat{G}\psi)$。又 $\hat{F}(\hat{G}\psi) \neq F(\hat{G}\psi)$，则 $\hat{G}\psi$ 不是 $\hat{F}$ 的本征态，∴ $\hat{G}\psi$ 和 $\psi$ 不是同一个态，即 $E$ 对应至少两个态，能级简并。

## 表象变换与矩阵力学

设 $F=(A_1, A_2, \cdots, A_n)$ 是一组力学量完全集，$|k\rangle$ 是其共同本征态，其中 $k$ 表征所有量子数。$|k\rangle$ 是正交归一的，满足 $\langle k|m\rangle = \delta_{km}$（$k=m$ 时为 1），$|k\rangle$ 是完备的，即体系中任一量子态可按 $|k\rangle$ 展开。

$\{|k\rangle\}$ 构成一个表象，可称为 $F$ 表象。$F$ 构成无穷维的希尔伯特空间，量子态是希尔伯特空间中的一个矢量，$|\psi\rangle = \sum_k a_k |k\rangle$，则 $a_k = \langle k|\psi\rangle$ 为内积，也可视为投影。

### 表象间的转化

角向方程：  
$$\sin\theta \frac{d}{d\theta}\left(\sin\theta \frac{d\Theta}{d\theta}\right) + \left(\sin^2\theta \frac{\partial^2}{\partial \phi^2}\right) \Theta = -l(l+1)\sin^2\theta \, \Theta$$

$F$ 表象中，$|\psi\rangle = \sum_k a_k |k\rangle$，$|\psi\rangle$ 在 $F$ 表象中可用系数列向量表示为 $a$。

$a'$ 与 $a$ 的转化实际上是基矢之间的转化。

$|\psi\rangle = \sum_k a_k |k\rangle = \sum_\beta a'_\beta |\beta\rangle$，$|k\rangle = \sum_\beta \langle \beta|k\rangle |\beta\rangle$（$|k\rangle$ 按 $|\beta\rangle$ 展开），从而统一基矢为 $|\beta\rangle$。

则 $a'_\beta = \sum_k \langle \beta|k\rangle a_k$，记 $S_{\beta k} = \langle \beta|k\rangle$，$S$ 为变换矩阵。

**注**：$a$、$a'$ 均为系数列向量，与本征态形式相似但意义完全不同。$|k\rangle$ 在希尔伯特空间中可表示为一个列向量，$|\psi\rangle$ 按 $|k\rangle$ 展开所得系数列为 $a$。

从矢量的角度考虑，$|\psi\rangle$ 是列向量 $e_1, e_2, \cdots$ 的线性组合。要消去基矢，则基矢之间的变换关系为 $S$ 矩阵。

由正交归一性：
$$\langle k'|k\rangle = \delta_{k'k}, \quad \langle k|k\rangle = 1, \quad |k\rangle = \sum_\beta S_{\beta k}|\beta\rangle$$

$$\langle k'|k\rangle = \left(\sum_\beta S_{\beta k'}\langle \beta|\right)\left(\sum_{\beta'} S_{\beta' k}|\beta'\rangle\right) = \sum_\beta S_{\beta k'}^* S_{\beta k} = \delta_{k'k}$$

$$\langle m|k\rangle = \left(\sum_\beta S_{\beta m}\langle \beta|\right)\left(\sum_{\beta'} S_{\beta' k}|\beta'\rangle\right) = \sum_\beta S_{\beta m}^* S_{\beta k} = 0 \Rightarrow S^\dagger S = SS^\dagger = I$$

**$S$ 为幺正矩阵。**

基矢变换关系：
$$(e'_1, e'_2, \cdots, e'_k, \cdots) = (e_1, e_2, \cdots, e_k, \cdots) S$$

即

③ 本征态的封闭性  
称为投影算符的封闭性。  
完备性 & 封闭性：强调重点不同，完备性指任意 \( |\psi\rangle \) 可按 \( \{|k\rangle\} \) 展开，封闭性指数学上封闭性。
$$\begin{pmatrix} \langle e'_1|e_1\rangle & \langle e'_1|e_2\rangle & \cdots & \langle e'_1|e_k\rangle \\ \langle e'_2|e_1\rangle & \langle e'_2|e_2\rangle & \cdots & \langle e'_2|e_k\rangle \\ \vdots & \vdots & \ddots & \vdots \\ \langle e'_k|e_1\rangle & \langle e'_k|e_2\rangle & \cdots & \langle e'_k|e_k\rangle \end{pmatrix} = S^\dagger$$

## 球谐函数与角向方程

上一页末尾涉及 $e^{i\phi}$ 与 $e^{-i\phi}$ 的组合，本页继续推导角向方程的解。

### 角向方程分离变量

考虑角向方程，令 $Y(\theta,\varphi)=\Theta(\theta)\Phi(\varphi)$：

$$
\sin\theta\frac{d}{d\theta}\left[\sin\theta\frac{d\Theta}{d\theta}\right]+\left(\lambda\sin^2\theta-m^2\right)\Theta=0
$$

分离变量得：

$$
\frac{d}{d\theta}\left[\sin\theta\frac{d\Theta}{d\theta}\right]+\lambda\sin^2\theta = -\frac{1}{\Phi}\frac{d^2\Phi}{d\varphi^2}=m^2
$$

### 方位角部分

$$
\frac{d^2\Phi}{d\varphi^2}+m^2\Phi(\varphi)=0 \Rightarrow \Phi_m(\varphi)=e^{im\varphi}
$$

### 极角部分（勒让德方程）

对于勒让德方程：

$$
\frac{1}{\sin\theta}\frac{d}{d\theta}\left[\sin\theta\frac{d\Theta}{d\theta}\right]+\left(\lambda-\frac{m^2}{\sin^2\theta}\right)\Theta(\theta)=0
$$

为使 $\Theta(\theta)$ 在区间 $[0,\pi]$ 有限，$\lambda$ 只能取 $\lambda=l(l+1)$。

**注意：** 仅当 $|m|\le l$ 时才有 $\Theta(\theta)\neq 0$，即 $m=0,\pm1,\cdots,\pm l$。

### 球谐函数

归一化条件：

$$
\int_0^\pi \Theta(\theta)\sin\theta\,d\theta = 1
$$

归一化系数：

$$
N_{lm} = \sqrt{\frac{(2l+1)(l-|m|)!}{4\pi(l+|m|)!}}
$$

球谐函数：

$$
Y_{lm}(\theta,\varphi) = N_{lm} P_l^{|m|}(\cos\theta) e^{im\varphi}
$$

**球谐函数满足正交关系：**

$$
\int_0^{2\pi}\int_0^\pi Y_{lm}^*(\theta,\varphi)Y_{l'm'}(\theta,\varphi)\sin\theta\,d\theta\,d\varphi = \delta_{ll'}\delta_{mm'}
$$

其中 $P_l^m(\cos\theta)$ 为连带勒让德函数，$L^2$ 与 $L_z$ 具有共同本征函数系。

## 氢原子

径向方程：

$$\left[\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{d}{dr}\right)+\frac{2\mu}{\hbar^2}\left(E-V(r)\right)-\frac{l(l+1)}{r^2}\right]R(r)=0$$

其中 $V(r)=-\frac{e^2}{r}$，令 $k=\frac{\sqrt{-2\mu E}}{\hbar}$，则方程为：

$$\left[\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{d}{dr}\right)+\left(E+\frac{e^2}{r}\right)-\frac{l(l+1)}{r^2}\right]R(r)=0$$

引入约化径向波函数 $u(r)=rR_l(r)$，则 $u(r)$ 满足：

$$\left[\frac{d^2}{dr^2}+\left(E+\frac{e^2}{r}\right)-\frac{l(l+1)}{r^2}\right]u(r)=0$$

∵ $V(r)<0$，$R_l(r)\to 0$，$r\to\infty$ 时薛定谔方程约为 $\frac{d^2u}{dr^2}+Eu=0$，若 $E>0$，$u(r)$ 呈振荡形式，不满足束缚态，则 $E<0$。从能量角度分析，$E=V+K$，$K<V$，$E<0$。核与电子“双星模型”。

于是方程化为：

$$\left[\frac{d^2}{d\rho^2}+\frac{2}{\rho}-\frac{l(l+1)}{\rho^2}-\frac{1}{4}\right]u(\rho)=0$$

$\rho\to\infty$ 时，方程近似为 $\frac{d^2u}{d\rho^2}-\frac{1}{4}u(\rho)=0$，$u(\rho)\sim e^{-\rho/2}$。

$\rho\to 0$ 时，方程近似为 $\frac{d^2u}{d\rho^2}-\frac{l(l+1)}{\rho^2}u(\rho)=0$，$u(\rho)\sim \rho^{l+1}$。

利用渐进解，设 $u(\rho)=\rho^{l+1}e^{-\rho/2}v(\rho)$。

$v(\rho)$ 满足方程：

$$\rho v''+(2l+2-\rho)v'+[\beta-l-1]v(\rho)=0$$

为**合流超几何方程**。

$v(\rho)$ 有多项式解的条件是 $\beta-l-1=n_r$，即 $\beta=l+1+n_r$（$n_r=0,1,2,\dots$）。

$$n=l+1+n_r,\quad n=1,2,3,\dots$$

$$\beta=\frac{\mu e^2}{\hbar^2 k}=n \Rightarrow E_n=-\frac{\mu e^4}{2\hbar^2 n^2}$$

$l$ 的取值为 $0,1,2,\dots,n-1$；$m$ 的取值为 $-l,-(l-1),\dots,0,\dots,l$。能量本征态由 $(n,l,m)$ 表征。

**氢原子轨道角动量的取值**：

$$L^2=l(l+1)\hbar^2,\quad l=0,1,2,\dots,n-1$$

**氢原子轨道角动量 $z$ 方向的取值**：

$$L_z=m\hbar,\quad Y_{lm}(\theta,\phi)=m\hbar Y_{lm}(\theta,\phi)$$

径向波函数：

$$R_{nl}(r)=N_{nl}\left(\frac{2r}{na}\right)^l e^{-r/na}L_{n+l}^{2l+1}\left(\frac{2r}{na}\right)$$

归一化条件：

$$\int_0^\infty |R_{nl}(r)|^2 r^2 dr=1$$

**能级简并**：$n=n_r+l+1$，能级简并度 $\sum_{l=0}^{n-1}(2l+1)=n^2$。

**径向位置概率分布**：在 $(r,r+dr)$ 内概率为：

$$r^2 dr \int |\psi_{nlm}(r,\theta,\phi)|^2 \sin\theta\,d\theta\,d\phi = r^2 |R_{nl}(r)|^2 dr = |u_{nl}(r)|^2 dr$$

称为投影算符成的封闭性。

一（r）(）E）(sn $+s\r0$ ²θL $∂^{2
角向方程：sinθ$(sinθr8) 80 )+5m{\$