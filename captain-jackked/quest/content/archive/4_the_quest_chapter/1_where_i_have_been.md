---
snippet: Origins of the Quest methodology
theme: generic
---

Where I have been since 2018
========================================


> Origins of the Quest Methodology.

# Silence
Where have I been? In 2018, I was consistent — pushing weight and [blogging](/archive). Then life happened — job switches and increasing professional demands.

In 2019, I switched from being a Software Developer to a Quant at a bank. This transition resulted in 'implicit' learning of the fundamental principles of quantitative modeling and I realized... the methodologies I had already been cooking up for Jackked weren't far off from how a bank builds quantitative models.

This period gave me the confidence to formalize the mathematical foundations of my training philosophy. I discovered a 'magical constant' that maps the relationship between load and repetitions. It works universally, providing a single, coherent framework for strength that holds regardless of muscle group or body type. You may have noticed the origins of this discovery in the strength-to-reps relationship that I [penned over half a decade ago](/archive/3_3_workout_programming).

We're about to touch upon THE key concepts that started it all for me. Answering the fundamental question of "how to program one's workouts" and building a system out of it was NOT what I had in mind when I started this journey. I dived in, saw patterns that no one else was talking about and pushed a little deeper with a little bit of logic and rationale... here we are.

*Question: How do you decide how much to lift based on your recent performances?*

# The 3.2% Rule

## Simple Decay
Think of the 1-rep-max of a lift as your 100%.  A natural question is: what is the n-rep-max i.e. what is the maximum weight you can lift for n reps (given 100% is your 1-rm)?

More specifically, what is the maximum weight such that

* it is impossible to perform n + 1 reps with it AND
* it is impossible to perform n reps if you add any amount of weight to it?

Here is the relationship at the heart of the Jackked engine:

$$ nRM = \frac{1RM}{(1.0 + 0.032)^{(n - 1)}} $$

Put simply: **All else being equal, the Load decays by ~3.2% for every additional Rep performed.** The more curious reader may have noticed that this is along the lines of [existing RM calculators](https://en.wikipedia.org/wiki/One-repetition_maximum). But structuring it this particular way, as we shall see, serves as middle-ground across a wide range of applications

> **Understanding exponential decay**
>
> 1. Think of a bank that gives **3.2% interest**. If you put **$100** in, you get **$103.2** a year from now
>
> 2. Now imagine you had a target payout: suppose you want to receive **$100** one year from now. How much do you deposit today? The answer is ~$96.90  
> $$ \frac{100}{1.0 + 0.032} = 96.90 $$
>
> 3. What if you want that **$100** four years from now? How would you deposit right now? The answer is ~$88.16  
> $$ \frac{100}{(1.0 + 0.032)^4} = 88.16 $$

## Now, Barbell Math
While lifting, your **1RM** is the $100 payout you desire. But you're smart and **NOT** willing to hit 1RMs directly — you want to be, say, 4 reps away and do safer 5RMs. So, how much do you lift to display an equivalent performance? The answer is **~88kg** (`100kg / 1.032^4`) because 5 reps vs 1 rep is like a '4yr gap'.

Conversely, if you know you can lift **88kg** for **5 reps**, you can estimate your 1RM without ever testing it. Just multiply by the gap: `88kg * 1.032^4 ≈ 100kg`. This allows us to normalize any *single maximal* set, whether it's 5 reps or 12 reps, back to a single 'Strength' metric. Any maximal set can now be a proxy for an actual 1 rep max.

We dive deeper and test the resilience of this line of thinking even in more complex situations — sub-maximal sets, intensity scaling, multi-set fatigue modeling — in [The Jackked Model](/archive/4_2_the_jackked_model).

# The Pandemic
All was well and then, COVID-19 hit. The pandemic forced a sabbatical from physical training and I wasn't able to fully experience the power of the Jackked 2.0 method. But my Quests didn't stop, they pivoted. I traded the barbell for a keyboard and dived into LeetCoding.

Back in 2019, a close friend of mine challenged me with a LeetCode problem. For context, I'd never once visited a single 'Coding Practice' website in my entire life. I was 4 yrs into Software Development and my 'Data Structures and Algorithms' knowledge came from the countably few extra courses I had done back in college (yup, not a CS major). So I created an account and began something - a journey that I did not expect would have as much impact on my life as it did. Yes, it more than tripled my already decent salary over the course of the next 5 yrs - but that's secondary. The three biggest wins came as follows:

* **Engagement**: In the TikTok era, LeetCoding was my antidote to doom-scrolling — real accomplishment instead of empty dopamine.
* **Better Developer**: If your 50-line LeetCode solution isn't readable, your 10,000-line production codebase doesn't stand a chance.
* **Neural Connections**: The gym fights sarcopenia. Algorithmic thinking fights cognitive rust. And that level of pattern recognition doesn't stay in a LeetCode tab — it bleeds into everything.

> Benefits aside, leetcoding sounds like a drag. A chore. Surely this wasnt fun?

Quite the opposite. I'm the guy who cannot do anything if it's not fun. That isn't to say I'm lazy. No, I make every effort to try and make things fun. Most things just aren't, despite trying (running on a treadmill ugh). But leetcoding is. All it needs it a tiny bit of gamifying.

Based on all the progressive overload related questions I'd been tackling in the lifting world, I stumbled upon a system — one that made NOT gaining LeetCode-solving momentum an impossibility. It starts with a simple question:

*How do you decide which problem to solve next, given 3,500+ options?*

Between 2019 and 2021, I pumped my numbers up from 600 to **2,500 solved problems** — never once looking at a solution or a guide. This was more than hobbyist coding; it was 'working the mind out' using the same intensity and discipline I had applied to the gym. It was during this period that the **Crackked Methodology** was born — applying progressive overload to build algorithmic fluency. I'd have problems in my TODO list for 2 years, out of nowhere something would click while I was asleep and I'd wake up with solutions to hard problems. I could FEEL the neural connections forming. How??

We explore this system — the crux being 'How to rate any LeetCode problem?' — in The Crackked Model (coming soon).

# The AfterMATH
As the world reopened, I faced a new challenge: regaining two years of lost strength and muscle. I applied the newly-devised **Jackked** methodology blindly. Within months, I hadn't just reclaimed my former self; I was setting new PRs. The system worked.

I emerged on the other side of COVID with the ability to grow my mind and my body. These discoveries have since been formalized into two apps — [Jackked](/scrolls/3_1_jackked) for strength training and [Crackked](/scrolls/3_2_crackked) for algorithmic thinking. Both are now available on <a href="https://play.google.com/store/apps/developer?id=Quest+Path">Google Play</a> and the <a href="https://apps.apple.com/us/developer/anand-kesavan/id1879453353">App Store</a>.
