# 科技

## 常见对易恒等式

$$[A, B] = -[B, A]$$

$$[A, B+C] = [A, B] + [A, C]$$

$$[A, BC] = [A, B]C + B[A, C]$$

$$[AB, C] = A[B, C] + [A, C]B$$

$$[A, B+C] + [B, A+C] + [C, A+B] = 0$$

$$[A, [B, C]] + [B, [C, A]] + [C, [A, B]] = 0 \quad (\text{对称})$$

④常见对易恒等式

Y OF SCIENCE AND TECHNOLOGY HUAZHONG UNIVERSITY OF SCIENCE AND TECHNOLOGY


## 利用对易关系求解平均值问题

HUAZHONG UNIVERSITY OF SCIENCE AND TECHNOLOGY

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

**方法：** 将本征态对应的算符尽量转化到最左/右边，直接作用到态矢上。

## 不确定度关系的严格证明

任意给定力学量 $A$ 和 $B$，对应的厄米算符为 $\hat{A}$ 和 $\hat{B}$，分别具有不确定度 $\Delta A$ 和 $\Delta B$，则有以下关系：

$$\Delta A \cdot \Delta B \geq \frac{1}{2}|\langle[\hat{A}, \hat{B}]\rangle|$$

其中 $\Delta A = \sqrt{\langle \hat{A}^2 \rangle - \langle \hat{A} \rangle^2}$，$\Delta B = \sqrt{\langle \hat{B}^2 \rangle - \langle \hat{B} \rangle^2}$。

令 $x = \hat{A} - \langle \hat{A} \rangle$，$y = \hat{B} - \langle \hat{B} \rangle$，要证变为 $\overline{x^2} \cdot \overline{y^2} \geq \frac{1}{4}|\langle[x, y]\rangle|^2$，联想 $b^2 \geq 4ac$。

考虑 $|\phi\rangle = (\alpha \hat{A} + i\beta \hat{B})|\psi\rangle$，$\langle\phi|\phi\rangle \geq 0$：

$$\langle\phi|\phi\rangle = \langle\psi|(\alpha \hat{A} - i\beta \hat{B})(\alpha \hat{A} + i\beta \hat{B})|\psi\rangle$$

$\hat{A}$、$\hat{B}$ 为厄米算符，展开得：

$$= \alpha^2\langle\hat{A}^2\rangle + \beta^2\langle\hat{B}^2\rangle + i\alpha\beta\langle[\hat{A}, \hat{B}]\rangle \geq 0$$

$\because \forall \alpha, \beta$，$\langle\phi|\phi\rangle \geq 0$，$\therefore |\langle[\hat{A}, \hat{B}]\rangle|^2 \leq 4\langle\hat{A}^2\rangle\langle\hat{B}^2\rangle$，即 $\overline{x^2} \cdot \overline{y^2} \geq \frac{1}{4}|\langle[x, y]\rangle|^2$。

$$\Rightarrow \Delta A \cdot \Delta B \geq \frac{1}{2}|\langle[\hat{A}, \hat{B}]\rangle|$$

**注意：** 对任意力学量 $A$、$B$，任意量子态 $|\psi\rangle$，若 $A$ 与 $B$ 不对易即 $[\hat{A}, \hat{B}] \neq 0$，则 $\Delta A$ 和 $\Delta B$ 不能同时为零，也即 $A$ 与 $B$ 不能同时测定。

## 共同本征函数

设 $\hat{A}\psi_a = A_a \psi_a$，$\hat{B}\psi_b = B_b \psi_b$。若 $[\hat{A}, \hat{B}] \neq 0$，则 $\psi_a$ 不是 $\hat{B}$ 的本征函数，$\psi_b$ 不是 $\hat{A}$ 的本征函数。

若 $[\hat{A}, \hat{B}] = 0$，则可能存在 $\psi$，使 $\hat{A}\psi = A\psi$，$\hat{B}\psi = B\psi$，此时称 $\psi$ 为 $A$ 和 $B$ 的共同本征函数。

**定理：** 设 $\hat{A}|k\rangle = a_k |k\rangle$，另有 $\hat{B}$，若 $[\hat{A}, \hat{B}] = 0$，且 $a_k$ 不简并（即 $a_k$ 只对应一个本征态 $|k\rangle$），则 $|k\rangle$ 也是 $\hat{B}$ 的本征态，即 $A$ 和 $B$ 拥有共同本征态。

**证明：** $[\hat{A}, \hat{B}] = 0 \Rightarrow \hat{A}\hat{B} = \hat{B}\hat{A}$，$\hat{B}\hat{A}|k\rangle = \hat{B} \cdot a_k |k\rangle = a_k \hat{B}|k\rangle$。则 $\hat{A}(\hat{B}|k\rangle) = a_k(\hat{B}|k\rangle)$，$\therefore \hat{B}|k\rangle$ 也是 $A$ 属于本征值 $a_k$ 的本征态，故 $\hat{B}|k\rangle$ 与 $|k\rangle$ 是一个量子态，即 $\hat{B}|k\rangle = b_k |k\rangle$。$A$、$B$ 拥有共同本征态 $|k\rangle$。

**例：** $\psi(\vec{r}) = \frac{1}{(2\pi\hbar)^{3/2}} e^{i\vec{p}\cdot\vec{r}/\hbar}$ 为 $\hat{p}_x$、$\hat{p}_y$、$\hat{p}_z$ 的共同本征函数，本征值为 $p_x$、$p_y$、$p_z$。

## 厄米算符本征值与本征态的特性

**转置算符：** 对任意 $\psi$ 和 $\varphi$，若 $\langle\psi|\hat{A}|\varphi\rangle = \langle\varphi|\hat{A}|\psi\rangle^*$，则称 $\hat{A}$ 和 $\hat{A}^T$ 互为彼此的转置算符。

**共轭算符：** 对算符 $\hat{A}$ 的每一元素取复共轭，得到 $\hat{A}^*$ 为 $\hat{A}$ 的共轭算符。

**厄米算符：** $\hat{A} = \hat{A}^\dagger = (\hat{A}^*)^T$，则称 $\hat{A}$ 为厄米算符。

**定理：** 厄米算符 $\hat{A}$ 在任意量子态下的平均值 $\bar{A}$ 为实数，$\hat{A}^2$ 的平均值 $\overline{A^2} \geq 0$。

**证明：** $\langle\psi|\hat{A}|\psi\rangle = \langle\psi|\hat{A}|\psi\rangle^* = \langle\psi|\hat{A}^\dagger|\psi\rangle = \langle\psi|\hat{A}|\psi\rangle$，$\therefore \bar{A} = \bar{A}^*$，$\bar{A}$ 为实数。

$$\langle\psi|\hat{A}^2|\psi\rangle = \langle\psi|\hat{A}\hat{A}|\psi\rangle = \langle\hat{A}\psi|\hat{A}\psi\rangle = \langle\varphi|\varphi\rangle \geq 0, \quad |\varphi\rangle = \hat{A}|\psi\rangle$$

### 厄米算符本征值的实数性

$\hat{F}|k\rangle = \lambda_k |k\rangle$，则 $\langle k|\hat{F}|k\rangle = \bar{F} = \langle k|\lambda_k |k\rangle = \lambda_k \langle k|k\rangle = \lambda_k$，$\therefore \lambda_k = \bar{F}$ 为实数（$\langle k|k\rangle = 1$）。

### 厄米算符本征态的正交性与完备性、封闭性

**① 厄米算符属于不同本征值的本征态必然正交**（对不同 $|k\rangle$ 可能有不同的 $\lambda$）：

$\hat{F}|k\rangle = \lambda_k |k\rangle$，$\hat{F}|k'\rangle = \lambda_{k'} |k'\rangle$。

$$\langle k'|\hat{F}|k\rangle = \lambda_k \langle k'|k\rangle, \quad \langle k'|\hat{F}|k\rangle = \langle k'|\hat{F}|k\rangle^* = \lambda_{k'} \langle k'|k\rangle$$

又 $\lambda_k$ 为实数，$\therefore \lambda_k = \lambda_k^*$，$\lambda_k \langle k'|k\rangle = \lambda_{k'} \langle k'|k\rangle$，而 $\lambda_k \neq \lambda_{k'}$，$\therefore \langle k'|k\rangle = 0$，即 $|k\rangle$ 与 $|k'\rangle$ 正交。

**② 本征态的完备性**

$\hat{P}_k = |k\rangle\langle k|$ 为投影算符，$\hat{P}_k = \hat{P}_k^\dagger$。

若对任意 $|\psi\rangle$，有 $\sum_k \hat{P}_k |\psi\rangle = \sum_k |k\rangle\langle k|\psi\rangle = |\psi\rangle$，则称基矢 $|k\rangle$ 具有完备性（任意 $|\psi\rangle$ 可按 $|k\rangle$ 展开）。

记 $c_k = \langle k|\psi\rangle$，则 $|\psi\rangle = \sum_k |k\rangle\langle k|\psi\rangle = \sum_k c_k |k\rangle$，$c_k$ 为用 $|k\rangle$ 将 $|\psi\rangle$ 做展开时的展开系数。

**定理：** 哈密顿算符 $\hat{H}$ 为厄米算符，满足本征方程 $\hat{H}|k\rangle = E_k |k\rangle$。对体系的任一归一化态 $|\psi\rangle$，若 $\langle\psi|\hat{H}|\psi\rangle$ 有下界（总大于某常数）但无上界，则 $\hat{H}$ 的本征态 $|k\rangle$ 的集合构成体系的一个完备集，即体系的任一量子态 $|\psi\rangle$ 可用 $|k\rangle$ 来展开。

### ③ 本征态的封闭性

$\hat{I}$ 为单位算符，$\hat{I}|\psi\rangle = |\psi\rangle$。

若本征态或基矢 $|k\rangle$ 满足 $\sum_k |k\rangle\langle k| = \hat{I}$，称为本征态或基矢 $|k\rangle$ 的封闭性；$\sum_k \hat{P}_k = \sum_k |k\rangle\langle k| = \hat{I}$ 称为投影算符的封闭性。

**完备性 & 封闭性：** 强调重点不同，完备性指任意 $|\psi\rangle$ 可按 $\{|k\rangle\}$ 展开，封闭性指数学上封闭性方程 $\sum_k |k\rangle\langle k| = \hat{I}$ 成立，两者相互依存。

**例：** 设体系的能量本征方程为 $\hat{H}|k\rangle = E_k |k\rangle$，证明哈密顿算符可表示为 $\hat{H} = \sum_k E_k |k\rangle\langle k|$（本征态具有完备性、封闭性）。

**证明：** $\hat{H}\sum_k |k\rangle\langle k| = \sum_k E_k |k\rangle\langle k|$，则 $\hat{H} = \hat{H}\sum_k |k\rangle\langle k| = \sum_k E_k |k\rangle\langle k|$。

## 守恒量与能级简并度

### 力学量平均值的时间依赖特性

$$\bar{A}(t) = \langle\psi(t)|\hat{A}|\psi(t)\rangle$$

薛定谔方程：$i\hbar\frac{\partial}{\partial t}|\psi(t)\rangle = \hat{H}|\psi(t)\rangle$。在左矢空间中：$-i\hbar\frac{\partial}{\partial t}\langle\psi| = \langle\psi|\hat{H}$。

$$\frac{d\bar{A}}{dt} = \frac{\partial}{\partial t}\langle\psi|\hat{A}|\psi\rangle + \langle\psi|\frac{\partial \hat{A}}{\partial t}|\psi\rangle + \langle\psi|\hat{A}\frac{\partial}{\partial t}|\psi\rangle = -\frac{1}{i\hbar}\langle\psi|\hat{H}\hat{A}|\psi\rangle + \langle\psi|\frac{\partial \hat{A}}{\partial t}|\psi\rangle + \frac{1}{i\hbar}\langle\psi|\hat{A}\hat{H}|\psi\rangle$$

$$= \frac{1}{i\hbar}\langle\psi|[\hat{A}, \hat{H}]|\psi\rangle + \langle\psi|\frac{\partial \hat{A}}{\partial t}|\psi\rangle$$

若 $\frac{\partial \hat{A}}{\partial t} = 0$（$\hat{A}$ 不显含 $t$）且 $[\hat{A}, \hat{H}] = 0$，则 $\frac{d\bar{A}}{dt} = 0$，$\bar{A}$ 与时间无关，$A$ 在任何态 $|\psi(t)\rangle$ 下的平均值 $\bar{A}$ 都不随时间改变。

### 守恒量

$A$ 在任何态 $|\psi(t)\rangle$ 下的平均值 $\bar{A}$ 都不随 $t$ 改变，则称此时 $A$ 对应的力学量为体系的一个守恒量。

$$\frac{\partial \hat{A}}{\partial t} = 0 \text{ 且 } [\hat{A}, \hat{H}] = 0 \Rightarrow A \text{ 为守恒量}$$

**定理：** 若 $[\hat{F}, \hat{H}] = 0$，$[\hat{G}, \hat{H}] = 0$，但 $[\hat{F}, \hat{G}] \neq 0$，则体系的能级是简并的。（$F$、$G$ 为守恒量）

**证明：** $\hat{H}$ 有共同本征函数 $\psi_E$，$\hat{F}\psi_E = F\psi_E$，$\hat{H}\psi_E = E\psi_E$。$\because [\hat{G}, \hat{H}] = 0$，则 $\hat{H}(\hat{G}\psi_E) = \hat{G}\hat{H}\psi_E = E(\hat{G}\psi_E)$，即 $\hat{G}\psi_E$ 也是 $\hat{H}$ 属于 $E$ 的本征态。又 $\hat{F}(\hat{G}\psi_E) \neq F(\hat{G}\psi_E)$，则 $\hat{G}\psi_E$ 不是 $\hat{F}$ 的本征态，$\therefore \hat{G}\psi_E$ 和 $\psi_E$ 不是一个态，即 $E$ 对应至少两个态，能级简并。

## 表象变换与矩阵力学

设 $\hat{F} = (\hat{A}_1, \hat{A}_2, \cdots, \hat{A}_n)$ 是一组力学量完全集，$|k\rangle$ 是其共同本征态，其中 $k$ 表征所有量子数。

$|k\rangle$ 是正交归一的，满足 $\langle k|m\rangle = \delta_{km} = \begin{cases} 1, & k = m \\ 0, & k \neq m \end{cases}$，$|k\rangle$ 是完备的，即体系中任一量子态可按 $|k\rangle$ 展开。

$\{|k\rangle\}$ 构成一个表象，可称为 $F$ 表象。$F$ 构成无穷维的希尔伯特空间，量子态是希尔伯特空间中的一个矢量，$|\psi\rangle = \sum_k a_k |k\rangle$，则 $a_k = \langle k|\psi\rangle$ 为内积，也可视为投影。

### 表象间的转化

$F$ 表象中，$|k\rangle = \psi_k$，$|\psi\rangle = \sum_k a_k |k\rangle$，$|\psi\rangle$ 在 $F$ 表象中可用系数列向量表示为 $a$。

$a'$ 与 $a$ 的转化实际上是基矢之间的转化。

$|\psi\rangle = \sum_k a_k |k\rangle = \sum_\beta a'_\beta |\beta\rangle$，$|k\rangle = \sum_\beta \langle\beta|k\rangle \cdot |\beta\rangle$（$|k\rangle$ 按 $|\beta\rangle$ 展开），从而统一基矢为 $|\beta\rangle$。

则 $a'_\beta = \sum_k a_k \langle\beta|k\rangle$，记 $S_{\beta k} = \langle\beta|k\rangle$，$S$ 为变换矩阵。

**注意：** $a$、$a'$ 均为系数列向量，与本征态形式相似但意义完全不同。$|k\rangle$ 在希尔伯特空间中可表示为一个列向量，$|\psi\rangle$ 按 $|k\rangle$ 展开所得系数列为 $a$。

从矢量的角度考虑，$|\psi\rangle = (e_1, e_2, \cdots, e_k, \cdots)$ 列向量 $e_k$ 的线性组合。

$\langle k'|k\rangle = \delta_{k'k}$，$\langle k|k\rangle = 1$，$|k\rangle = \sum_\beta S_{\beta k}|\beta\rangle$，$\langle k'|k\rangle = (\sum_\beta S_{\beta k'}^*\langle\beta|)(\sum_{\beta'} S_{\beta' k}|\beta'\rangle) = \sum_\beta S_{\beta k'}^* S_{\beta k} = \delta_{k'k}$

$$\Rightarrow S^\dagger S = SS^\dagger = I$$

$S$ 为幺正矩阵。

## 氢原子

### 径向方程与角向方程

$$\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) + \left[\frac{2\mu}{\hbar^2}(E - V(r)) - \frac{l(l+1)}{r^2}\right]R(r) = 0$$

角向方程：

$$\frac{1}{\sin\theta}\frac{\partial}{\partial\theta}\left(\sin\theta\frac{\partial Y}{\partial\theta}\right) + \frac{1}{\sin^2\theta}\frac{\partial^2 Y}{\partial\varphi^2} + \lambda Y = 0$$

**① 考虑角向方程** $Y(\theta, \varphi) = \Theta(\theta)\Phi(\varphi)$：

$$\frac{1}{\sin\theta}\frac{d}{d\theta}\left(\sin\theta\frac{d\Theta}{d\theta}\right) + \left(\lambda - \frac{m^2}{\sin^2\theta}\right)\Theta = 0$$

$$\frac{d^2\Phi}{d\varphi^2} + m^2\Phi(\varphi) = 0 \Rightarrow \Phi_m(\varphi) = \frac{1}{\sqrt{2\pi}}e^{im\varphi}$$

对于勒让德方程 $\frac{1}{\sin\theta}\frac{d}{d\theta}\left(\sin\theta\frac{d\Theta}{d\theta}\right) + \left(\lambda - \frac{m^2}{\sin^2\theta}\right)\Theta(\theta) = 0$，为使 $\Theta(\theta)$ 在区间 $[0, \pi]$ 有限，$\lambda$ 只能取 $l(l+1)$。

$|m| \leq l$ 时才有 $\Theta(\theta) \neq 0$，$\Rightarrow m = 0, \pm 1, \cdots, \pm l$。

$$\Theta_{lm}(\theta) = N_{lm} P_l^m(\cos\theta), \quad N_{lm} = \sqrt{\frac{(2l+1)(l-|m|)!}{2(l+|m|)!}}$$

$$Y_{lm}(\theta, \varphi) = \Theta_{lm}(\theta)\Phi_m(\varphi) = N_{lm} P_l^m(\cos\theta)e^{im\varphi}$$

球谐函数满足正交关系：

$$\int_0^{2\pi}\int_0^\pi Y_{lm}^*(\theta, \varphi)Y_{l'm'}(\theta, \varphi)\sin\theta\,d\theta\,d\varphi = \delta_{ll'}\delta_{mm'}$$

### 氢原子径向方程

$$V(r) = -\frac{e^2}{r}$$

引入约化径向波函数 $u(r) = rR_l(r)$，则 $u(r)$ 满足：

$$\frac{d^2u}{dr^2} + \left[\frac{2\mu}{\hbar^2}\left(E + \frac{e^2}{r}\right) - \frac{l(l+1)}{r^2}\right]u(r) = 0$$

$\because V(r) < 0$，$R_l(r) \to 0$，$r \to \infty$ 时薛定谔方程约为 $\frac{d^2u}{dr^2} + \frac{2\mu E}{\hbar^2}u = 0$，若 $E > 0$，$u(r)$ 呈振荡形式，不满足束缚态，则 $E < 0$。从能量角度分析，$E = V + K$，$K < |V|$，$E < 0$。核与电子"双星模型"。

利用渐进解，设 $u(\rho) = \rho^{l+1}e^{-\rho/2}v(\rho)$。

$v(\rho)$ 满足方程 $\rho\frac{d^2v}{d\rho^2} + (2l+2-\rho)\frac{dv}{d\rho} + [\beta - l - 1]v(\rho) = 0$，为合流超几何方程。

$v(\rho)$ 有多项式解的条件是 $\beta - l - 1 = n_r$，$\beta = l + 1 + n_r$（$n_r = 0, 1, 2, \cdots$）。$n = l + 1 + n_r$，$n = 1, 2, \cdots$。

$$E_n = -\frac{\mu e^4}{2\hbar^2 n^2}$$

$l$ 的取值为 $0, 1, \cdots, n-1$；$m$ 的取值为 $-l, -(l-1), \cdots, 0, \cdots, l$。能量本征态由 $(n, l, m)$ 表征。

氢原子轨道角动量的取值：$\hat{l}^2 = l(l+1)\hbar^2$。

氢原子轨道角动量 $z$ 方向的取值：$\hat{l}_z = m\hbar$，$\hat{l}_z Y_{lm} = m\hbar Y_{lm}$。

归一化条件：$\int_0^\infty |R_{nl}(r)|^2 r^2 dr = 1$。

能级简并：$n = n_r + l + 1$，能级简并度 $\sum_{l=0}^{n-1}(2l+1) = n^2$。

径向位置概率分布：在 $(r, r+dr)$ 内概率为 $r^2 dr \int |\psi_{nlm}(r, \theta, \varphi)|^2 \sin\theta\,d\theta\,d\varphi = r^2 |R_{nl}(r)|^2 dr = |u_{nl}(r)|^2 dr$。

$e{}e{)$ (ek，e{2}) ∴（eke)
1701572 华be_大附印刷
[Tab]

2²[s（sθ)((]
一（r）(）E）(sn $+s\r0$ ²θL \$∂^{2

(n-2k）（22-1) \$(-1）{n (可通过递推+母函数求解)

角向方程：sinθ$(sinθr8) 80 )+5m{$