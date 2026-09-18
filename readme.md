The script is designed for the bibliography you pasted. It handles @article, @book, @misc, @inproceedings, conference papers, web pages, electronic articles, multiline authors and keywords, nested BibTeX braces, Markdown ```bibtex fences, and stray text between entries. It also preserves the BibTeX citation key as the EndNote %F Label.

Run it like this:

python bibtex_to_endnote.py references.bib references.enw

For example, this:

```LaTeX
@article{healthcare_evaluation_2024_578,
   author = {Abbasian, Mahyar and Khatibi, Elahe and Azimi, Iman},
   title = {Foundation metrics for evaluating effectiveness of healthcare conversations powered by generative AI},
   journal = {NPJ Digital Medicine},
   volume = {7},
   number = {1},
   pages = {82},
   year = {2024},
   type = {Journal Article}
}
```

becomes:

```YAML
%0 Journal Article
%F healthcare_evaluation_2024_578
%A Abbasian, Mahyar
%A Khatibi, Elahe
%A Azimi, Iman
%T Foundation metrics for evaluating effectiveness of healthcare conversations powered by generative AI
%J NPJ Digital Medicine
%D 2024
%V 7
%N 1
%P 82
```
