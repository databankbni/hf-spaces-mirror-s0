---
snippet: Fatigue management between reps, sets and sessions
---

The Jackked Model
========================================


In [The Quest Story](/archive/4_1_where_i_have_been), we introduced the 3.2% rule — the observation that load decays by ~3.2% for every additional rep. Here, we stress-test that idea.

*Question: How do you decide how much to lift based on your recent performances?*

# The 3.2% Rule

## Sub-Maximal Sets
Most training isn't (read: shouldn't be) done to failure. In that case, how does the decay rule from above apply? That was all about max sets!

Here is where we talk about 'intensity' of a set — which is measured as 'Reps in Reserve' (RIR)

* Think about performing a 5 rep set with your current 7 rep max. Such a set is said to have a 2-RIR intensity
* You can see where we are going with this: maximal sets are a special case i.e. 0-RIR sets. What we saw earlier was the relationship between two 0-RIR sets varying in the number of reps

Now we take things one step further, making the relationship:

$$ Wt(n, x) = \frac{Wt(1, x)}{(1.0 + 0.032)^{(n - 1)}}, \\
\text{where } Wt(n, x) \text{ is the weight you can lift for } n \text{ reps with } x \text{ RIR} $$

Put simply: **the Load decays by ~3.2% for every additional Rep performed while maintaining the same intensity**

We are extending the relationship between max sets to now 'equal-intensity' sets. The same math as before applies. If you did 88kg for 5 reps and felt like you could do 3 more reps, you can probably do 100kg for 1 rep and feel like you had 3 reps in reserve*.

**This is assuming, of course, that you have no apprehensions or 'skill issue' with either of the two loads. We will deal with such caveats soon.*

## The Generalized Decay

What is the relationship between a 3-RIR set and a 4-RIR set?

> Well, if you took a 3-RIR set and performed 1 rep less, it would be a 4-RIR set (by definition).

But that's not what we're after here. What we are really asking is — by how much do we need to change the load so that a 3-RIR set turns into a 4-RIR set?

> Well, for starters, the 4-RIR load would be lighter.

But how much lighter?

> Wait a second, we could
> 
> 1. take the 3-RIR set, reduce 1 rep, make it 4-RIR and then
> 2. apply our Level 2 rule, increase 1 rep, while maintaining 4-RIR
> 
> We have successfully changed the RIR and the load without changing Reps!

Let's take an example:  
1. If you could perform 100kg for 6 reps at 3-RIR, you could perform 100kg for 5 reps at 4-RIR
2. If 100kg for 5 is your 4-RIR set, what load for 6 reps would also be your 4-RIR set?

Easy — 96.90kg (100kg/1.032)

So the more general rule, using the same notation as before, goes something like:

$$ Wt(n, x) = \frac{Wt(m, y)}{(1.0 + 0.032)^{(n - m + x - y)}}, \\
\text{where } n \text{ and } m \text{ are reps and } x \text{ and } y \text{ are RIR} $$

> Yooo, that's so complex. How do you make sense of it??

Is it complex though? Look closely and you will see plain english emerging out of it. Imagine that n is larger than m and that x is larger than y.

> *If you want to perform more reps (m → n) or make your sets less intense (y → x), you have to decrease the load.*
> 
> 'n - m' is 'how much lighter' and 'x - y' is 'how much easier' the set is.

It's as simple as that!

## Multi-sets Utility

Everything we have discussed so far assumes 'isolated sets' — single sets performed in isolation.

> But that's not how real workout sessions are. We tend to perform multiple sets and almost always bundle sets of the same exercise together (unless it's a "oh I'm in a hurry, let me super set everything I need to do and get out of the gym" day). Surely performing a hard set of squats affects the strength expression for the sets that follow?

Absolutely, it does!

And there lies the challenge in applying percentage based laws to real workouts. An isolated 5RM calculation holds no meaning if we rarely perform isolated sets. Jackked tackles this challenge head-on. It has its own carefully calibrated methodology for estimating fatigue accumulated per set.

> Wait, is 'Fatigue' just a buzzword? Is this a technical term or are we just throwing fitness jargon?

It's somewhere in between:

1. Fatigue is something we all relate to. We know that we cannot perform back to back true max sets because the fatigue from the first one interferes with the second
2. At the same time, there is an idea with which we can quantify fatigue. Let's define accumulated fatigue as 'the expected drop in performance for the rest of the sets'

How it manifests:

* If you are performing max sets, a fatigue of '1.0' would decrease the reps performed in each of the max sets by 1 (as opposed to if the fatigue were 0, ie a fresh day)
* If you are performing sub-maximal sets, a fatigue of '1.0' would increase the intensity of those sets by 1 (remember RIR?)

## What Jackked does:
1. Keeps track of accumulated fatigue (ie pre-fatigue per set)
2. Accounts for pre-fatigue and adjust the load to match the target RIR

An example to illustrate how it all adds up:

How do we decide a single load for '3 sets of 8 with last set at RIR 1' session based on what we've established? For simplicity, let's assume each set adds 0.75 fatigue.

OK, so the RIR constraint is on the last set (it usually is). And after two sets, the pre-fatigue would be 1.5 (0.75 * 2).  
Logically, for the last set of 8 with a pre-fatigue of 1.5 to feel like a 1-RIR, the load should be your 10.5 rep max (ie 74.1% of 1rm). Yes, the model seamlessly accounts for fractional reps as well.

Here's how the 3 sets would look for someone with 100kg as their estimated 1rm:

* 74.1kg for 8 (at zero fatigue, 2.5 RIR)
* 74.1kg for 8 (at 0.75 fatigue, 1.75 RIR)
* 74.1kg for 8 (at 1.5 fatigue, 1 RIR)

This solves the standard 'How much to load' problem where most schools-of-training just give you one weight and hope you don't fail on set 3.

You can see how every piece in the puzzle can be broken down into first principles — every individual step is a rational extension of the previous. Together, they allow us to build this intricate and effective system.

# So what?

> What's the point of all this? Is working out meant to be this math-heavy?

The point of the 3.2% rule isn't to force complexity into a seemingly simple problem — 'what do I do at the gym?' On the contrary, it's there to simplify things down to their first principles.

Think about the endless debates online regarding the 'perfect' rep range or the 'ultimate' rep scheme. You'll find sources claiming 'The ONE detail stalling your growth' or 'Top 3 exercises to make your muscles explode.' None of them agree. Contradictions among 'experts' are the norm in lifting — and don't even get me started on general 'health and fitness'; that's a whole other mess. Why is there so much noise and clutter surrounding what you should actually focus on when you step under a barbell?

The base truth is likely closer to the over-simplified 'Go lift heavy weights' than anything catchy. But 'lift heavy' isn't glamorous enough to go viral. Content creators are forced to sell flashiness to survive the algorithm.

I don't claim to have the final word on the biomechanics of hypertrophy. My goal here is twofold:

1. Quantify the intuition: Add some numbers to the 'Go lift heavy' advice. I want to upgrade it with a layer of nuance based on high-school math, forming a foundation of lifting knowledge so solid that the fluff has a hard time infecting your mind.
2. Systematize the journey: Make the process safer, more effective and actually enjoyable.

If the world lost all knowledge of lifting tomorrow, 'Go lift heavy' would still be the most effective starting point. It's simple, effective and probably won't kill you. But why limit yourself to 'probably'?

Technology allows us to:

1. Pen down ideas in precise language (code)
2. Make glorified sand and metal (transistors) do the heavy lifting of calculation
3. Share these systems through applications

No one wants to do math at the gym. Honestly, there are so many moving parts in this model that running the numbers is the last thing I want to do while gasping for air between sets. The Jackked app exists specifically to solve that friction. It accounts for the decay, the RIR and the fatigue on your behalf.

All you have to do is show up.

# The Two Problems

About how the 3.2% rule solves both

## 1. What and 'how much' to push?

Not everyone should have the same personal record (PR) goals. No, this is not some 'oh we are all special snowflakes and unicorns' argument. Even the same person's PR goals should vary from time to time. Anyone who has tried linear progression (like 5x5) knows how quickly things can get stale. You may prolong 'gains' by getting fat as you do the LP — but what's the point if being athletic is part of your end-goal and you'd have to shed the unnecessary flab (and all 'gains') anyway?

Even minor variations in the goal rep max have that psychological novelty effect. And who knows? Perhaps that variety is exactly what a specific muscle group in your body might physiologically need to push you through that plateau — considering that there is variation in the distribution of muscle fibre types even across muscles within the same person's body.

There is more: If you make a 5RM, you celebrate. Why can we not celebrate a 10RM as well? How about a 7RM? Think of your rep maxes as a line, a contour, you draw. Each time you hit a new RM, you push that contour at a specific point. Sure, the whole line moves by a little but the point you 'poked' sticks out more. How about evening that out a little and poking it at different places? Each poke is pushing the entire line by a little after all.

> Well, if all RMs are on the table, which one do I pick?

First of all, not 'all' RMs are available. At least not practically.

1. **You can't make 1RMs frequently** because it will fry you (very neurally taxing), there's too few reps to count as effective volume and failures with 1RMs can be risky without proper equipment.

2. **You really don't want to do super large sets** because only the last few reps are effective (waste of time) and too many reps means too little weight, making it easy to 'cheat' by using non-target muscles.

Once you account for that, you simply pick the one you're lagging the most in. You get the greatest 'bang for your buck' by choosing to hit a new PR within the desired rep range for the RM you're the weakest at.

> How do I know what's lagging?

Let Jackked do that for you. The Path tab of the app provides two rep-max curves:

1. Your real maxes (sets you have actually done)
2. Your 'potential' rep maxes — ie a conservative estimate on what you can do

Just look at the plots to figure out which RM is the lowest-hanging-fruit. If the gap between your real performance and your potential at 8 reps is huge, that's your target. You've already 'unlocked' that strength elsewhere; you just need to go claim it.

> What if I'm mentally fatigued and don't want to study graphs to set a new PR?

Reading these graphs is never a mandate. The workout program generated for you already has this feature embedded. The 'top sets' recommended are going to be based on whatever you're lagging with! It finds the 'weakest link' in your strength contour and puts it right in front of you.

To list out the benefits of this approach, in short:
* **Interconnected Progress:** Pushing a specific rep max likely improves your overall performance across the entire curve.
* **Delaying Saturation:** By rotating through these challenges, we delay the point where progress stalls — whether that's your mind getting bored or your body stopping responding to the same old stimulus.

## 2. How much work to do? How intense?

In the 'Setup' page of the app, while you select exercises for each movement pattern, you can choose a rep-scheme that fits your current goal. While there are many ways to train, I recommend sticking to 'Heavy', 'Moderate' or 'Volume'. They are specifically tuned to leverage the principles we've discussed.

We've already seen how Jackked uses cumulative fatigue to compute the exact weight for back-to-back sets. But how does that look in practice when you're standing in front of the rack? Let's dissect the 'Moderate' rep scheme to see the logic in action.

**Anatomy of a Rep Scheme: 'Moderate'**

1. The Probe (Top Set): The first set is designed to find that 'low-hanging fruit' we talked about. If the engine sees you are lagging on your 10RM, it will prescribe a load and a rep target specifically calculated to let you 'poke' that part of the curve by performing an AMRAP (As Many Reps As Possible) set here. This is your chance to turn 'potential' strength into 'real' strength by hitting a new 9, 10, 11 or even 12 rep max.
2. The Back-off (Volume Sets): Once you've poked the curve, the app shifts gears. It prescribes 2-3 sets of 8-9 reps to hit a total volume target (around 25 total reps).

'Volume' schemes use higher rep ranges (10-12) to accumulate more total work with less joint stress, while 'Heavy' schemes stay in the 5-7 range to focus on mechanical tension. Regardless of which you pick, the RIR (Reps in Reserve) for the top set and the final volume set is usually anchored around 2-4.

**Why this works: Precision over Guesswork**

Most programs give you a static weight and hope you don't hit a wall by the third set. Jackked goes a little deeper:

* Target Volume: It ensures you do enough work to actually trigger growth, without doing so much that you can't recover
* Target Intensity: It uses the 3.2% rule and the fatigue model to adjust the weight for every single set.

If you over-perform on your top set, the app knows you're 'hot' that day and will nudge the following sessions up. If the top set feels like a grind, it scales back due to an internally modeled 'natural decay' for the strength curve. It's a closed-loop system that ensures every rep you perform is 'effective volume' rather than just junk reps or dangerous ego-lifting.

By hitting a specific volume target with a precise RIR constraint, we remove the 'should I add 5lbs today?' anxiety. The math has already decided the optimal path; you just have to move the metal.
