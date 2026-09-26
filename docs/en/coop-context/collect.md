---
title: Collect
parent: CoopContext
grand_parent: English
nav_order: 1
lang: en
---

# Collect

Collect determines which retired Areas can proceed to GC. It produces a collection plan without modifying Context or removing Areas.

Collect tracks each Area's `EffectRange` and performs a right-to-left interval sweep. Overlapping ranges form one component; starting from the Context tail, a component is collectable only when every Area in it is retired.

![A tall prefix precedes two aligned ranges: a longer Area A and a shorter Area B.](../../assets/coop-context-collect.svg)

A and B have overlapping EffectRanges after the prefix:

- B is retired, A is retained: neither can be collected.
- Both A and B are retired: they can be collected together, preserving the prefix.

## Observation barrier

A retained Area with an `ObserveRange` but no `EffectRange` acts as an observation barrier. Collection can detach a tail only if it starts strictly after every such Area's observation start, keeping those observation boundaries valid.
