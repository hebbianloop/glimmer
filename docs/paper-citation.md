# How to cite Glimmer

If you use Glimmer in your research, cite the software revision you actually used. The architecture manuscript is unpublished; do not describe it as accepted conference proceedings:

```bibtex
@unpublished{eldamaty2026glimmer,
  title={Reproducibility as Knowledge Graph Navigation: Glimmer, a Research-Object Knowledge Base for AI-Native Neuroimaging Analysis},
  author={El Damaty, Shady},
  year={2026},
  note={Unpublished manuscript}
}
```

For the code, include the exact commit or an archived release identifier with your citation. The branch package is a development candidate:

```bibtex
@software{glimmer2026,
  title={Glimmer: a Research-Object Knowledge Base for AI-Native Scientific Workflows},
  author={El Damaty, Shady},
  url={https://github.com/hebbianloop/glimmer},
  version={0.6.0.dev1},
  year={2026}
}
```

The working manuscript that extends the architecture to **proactive provenance**
(executable run-records + the node runner) is drafted at
[`docs/paper-draft.md`](paper-draft.md).
