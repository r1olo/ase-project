TARGET=CarusiReport.pdf

build/${TARGET}: report.tex
	latexmk -pdf report.tex -outdir=build
	mv build/report.pdf build/${TARGET}
