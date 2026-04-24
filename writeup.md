# Evaluating LLM Reasoning on Minesweeper Puzzles

## Abstract

## Introduction
Large language models have shown a lot of capacity to engage in complex chains of reasoning during the process of generation, and I want to investigate how that translates to spatial puzzle solving.

Minesweeper is an excellent tool for the evaluation of these capabilities. The base game requires a spatial understanding of the relationship between clues and unknown information, and the amount of information known is constantly recontextualizing clues as the puzzle progresses. To add even further complexity to this, additional rules can be added on top of the puzzle. These rules will be able to modify the game in a few different ways, primarily changing the interpretation and relationships between individual clues or affecting the puzzle on a global scale. Generally, an understanding of how the supplamental rule applies to the puzzle will be necessary to complete it.

## Related Work

"Assessing Logical Puzzle Solving in Large Language Models: Insights from a Minesweeper Case Study" by Yinghao Li, Haorui Wang, and Chao Zhang.
This paper examined language models in a very similar context, with their conclusion saying that the models they tested were unable to succeed in much more than short logical chains. They also notably said that this was evidence against considering LLMs a intelligent object that will threaten human society. However, models have come a very long way since that paper was published in 2024, and my goal is to examine if LLMs are able to engage in longer chains of reasoning than at the time of that paper. My experiments will be structured in an extremely similar way, but introduce the idea of additional rules added on top of the base puzzles.


## Experiments

### What I've Done

So far the main thing I've accomplished is building the framework in which experiments will be conducted. I have scripts to generate and validate the solvability of puzzles, then ones that manage a boardstate during the process of prompting a language model. The interface for language models is also functioning, currently just using small locally run models downloaded off of HuggingFace to test feasability.

All of this data is saved in .jsonl files, which will eventually be used in my analysis but currently can just be used in the creation of an html dashboard that visually represents each puzzle and the steps taken to solve it by the player.

I have gotten some results from these small models, but ultimately they are just a test for if I can get a model to understand what's going on in my representation and give me an action in return and these results aren't very useful.

### What is next

The first step I'm going to take next is to switch to using Ollama for my local experiments. This should improve response time and allow me to be more flexible in trying things out or running a larger dataset. They will also likely produce better results than the very small models I've been using so far.

Next I want to expand my experimental framework slightly to ask for a reason each time the language model provides a move. This was done to good success in the referenced Minesweeper paper, and will likely be the basis of much of my analysis. It will let me go beyond just plain success rate of the models, and give access to a better method of comparison in performance.

After that is working locally, I will start experiments with larger models using an API. This is where the bulk of my useful experimental data will come from. My current plan for if these models perform significantly better than I expect is to transition the project to a comparison between them and the performance of the much smaller Ollama models, giving some insight into the emergent reasoning capabilities. Depending on the results, this may be interesting to include anyway.

Similar to the referenced Minesweeper paper, I built in the ability to manipulate the way in which the board is represented to the language model. For the purposes of my experiments, I am going to stick with the coordinate system that they reported worked best for them, but if I find myself with additional time I may experiment with changing this variable.


## Results
None yet, I will be publishing the dashboard using Github pages once I have more solid results from Ollama and API experimentation.

## Conclusion

Coming soon

## References

Coming soon, once I have time to write a .bib file and make this look nice.

## Appendix

Rules that may be tested:
1. There must be at least 1 mine in every 2x2 area
2. All mines are orthogonally or diagonally connected
3. Mines may not form a row of three orthogonally or diagonally
4. All non-mines are orthogonally connected, and all mines are orthogonally connected to the outside of the board
5. All mines must form 1x2 or 2x1 blocks. Blocks do not touch each other
6. All mines form a single snake whose body does not touch itself
7. The number of mines in each row and column is the same
8. No two mines can touch horizontally
9. The clue indicates the number of consecutive groups of mines in the neighboring 8 cells
10. Each clue is either one greater or one less than the actual value
11. The clue indicates the number of mines in a cross region within distance 2
