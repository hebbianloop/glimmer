# Build the paper with the shared house class one directory up.
TEXINPUTS := ..:$(TEXINPUTS)
export TEXINPUTS

main.pdf: main.tex refs.bib
	latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex

.PHONY: clean
clean:
	latexmk -C
	rm -f *.bbl
