% glimmer-paper.cls — house document class for Glimmer submittable papers.
%
% The standard for all submittable Glimmer manuscripts (see papers/README.md).
% A thin, venue-neutral layer over `article`: clean typography, a preprint banner,
% and a small set of title-block macros. Strip nothing venue-specific lives here,
% so a paper can be retargeted to a journal/conference template by swapping the
% \documentclass line, not by rewriting the body.
%
% Options:
%   preprint  — show a "Preprint — <date>" banner and DOI/repo line (default off)
%   draft     — show a "DRAFT — do not circulate" watermark line (default off)
%   11pt/12pt — passed through to article (default 11pt)
%
% Title-block macros: \affil{...}  \version{...}  \repo{...}
% Use \maketitle as usual; \begin{abstract}...\end{abstract} is provided.

\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{glimmer-paper}[2026/06/24 Glimmer house paper class]

\newif\ifglimmer@preprint \glimmer@preprintfalse
\newif\ifglimmer@draft    \glimmer@draftfalse
\DeclareOption{preprint}{\glimmer@preprinttrue}
\DeclareOption{draft}{\glimmer@drafttrue}
\DeclareOption*{\PassOptionsToClass{\CurrentOption}{article}}
\ExecuteOptions{}
\ProcessOptions\relax
\LoadClass[11pt]{article}

% --- geometry & typography ----------------------------------------------------
\RequirePackage[letterpaper,margin=1in]{geometry}
\RequirePackage[T1]{fontenc}
\RequirePackage{lmodern}
\RequirePackage{microtype}
\RequirePackage{amsmath,amssymb}
\RequirePackage{booktabs}
\RequirePackage{xcolor}
\definecolor{glimmerlink}{RGB}{30,86,150}
\RequirePackage[colorlinks=true,linkcolor=glimmerlink,citecolor=glimmerlink,urlcolor=glimmerlink]{hyperref}
\RequirePackage{enumitem}
\setlist{itemsep=2pt,topsep=3pt,parsep=0pt}
\RequirePackage{natbib}
\RequirePackage{titlesec}
\titleformat{\section}{\normalfont\large\bfseries}{\thesection}{0.6em}{}
\titleformat{\subsection}{\normalfont\normalsize\bfseries}{\thesubsection}{0.6em}{}
\setlength{\parskip}{0.4em}
\setlength{\parindent}{0pt}

% --- title-block macros -------------------------------------------------------
\newcommand{\glimmer@affil}{}
\newcommand{\affil}[1]{\renewcommand{\glimmer@affil}{#1}}
\newcommand{\glimmer@version}{}
\newcommand{\version}[1]{\renewcommand{\glimmer@version}{#1}}
\newcommand{\glimmer@repo}{}
\newcommand{\repo}[1]{\renewcommand{\glimmer@repo}{#1}}

% --- banners ------------------------------------------------------------------
\RequirePackage{fancyhdr}
\pagestyle{fancy}\fancyhf{}
\renewcommand{\headrulewidth}{0pt}
\fancyfoot[C]{\thepage}
\ifglimmer@preprint
  \fancyhead[C]{\footnotesize\color{gray}Preprint\ifx\glimmer@version\@empty\else\ — Glimmer v\glimmer@version\fi\ — \today}
\fi
\ifglimmer@draft
  \fancyhead[C]{\footnotesize\color{red}DRAFT — do not circulate — \today}
\fi

% Put the affiliation / version / repo line under the author block in \maketitle.
\let\glimmer@oldmaketitle\maketitle
\renewcommand{\maketitle}{%
  \glimmer@oldmaketitle
  \begingroup\centering\small
    \ifx\glimmer@affil\@empty\else\glimmer@affil\par\fi
    \ifx\glimmer@repo\@empty\else\texttt{\glimmer@repo}\par\fi
  \endgroup
  \vspace{0.5em}
}

\endinput
