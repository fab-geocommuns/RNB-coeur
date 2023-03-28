# Contributing to BatID-core

## Continuous Integration

This project uses the following integrations to ensure proper codebase maintenance:
- [Github Worklow](https://help.github.com/en/actions/configuring-and-managing-workflows/configuring-a-workflow) - run jobs for coverage

## Developing guidelines

#### Code quality 

- To run all quality checks together
(Note that in a sequence of comamnds, if one of the commands is false the Makefile will stop the execution)

```bash
make style
```

- To run quality check and perform modifications if needed

```bash
make apply-style
```