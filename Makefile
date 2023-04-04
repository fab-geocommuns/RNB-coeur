# Target to run quality check (only check, not updates)
# autoflake here might be redundant with flake 8
style:
	isort . -c
	flake8
	autoflake -r . 

# Target to run quality check and perform modifications if needed
apply-style:
	isort . 
	autoflake --in-place -r .

