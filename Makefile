JULIA ?= julia
JULIA_DEPOT_PATH ?= $(CURDIR)/.julia
JULIA_NUM_THREADS ?= auto
VERIFY_JULIA_NUM_THREADS ?= 2
EXPORT_JULIA_NUM_THREADS ?= 2
JULIA_RUN := JULIA_DEPOT_PATH=$(JULIA_DEPOT_PATH) JULIA_NUM_THREADS=$(JULIA_NUM_THREADS) $(JULIA) --startup-file=no --history-file=no --project=.
PYTHON ?= python3
TECTONIC ?=
TECTONIC_ARCHIVE ?=
TECTONIC_BUNDLE_URL := https://relay.fullyjustified.net/default_bundle_v33.tar
TECTONIC_BUNDLE_DIGEST := 6ffe055852f8faf66c0acbe1a7fb27f87b869a90bad1204f3bf4d9683f597c7c
SOURCE_DATE_EPOCH ?= 1789084800
RELEASE_REF ?= HEAD
RELEASE_TAG ?=
RELEASE_TAG_OPTION := $(if $(strip $(RELEASE_TAG)),--tag $(RELEASE_TAG),)
PROJECT := kissing-number-11-certified-upper-bound
VERSION := 0.1.0
PAPER_PDF := paper/$(PROJECT)-paper-v$(VERSION).pdf
ZENODO_RECORD_ID ?=
KN11_COMPACT_WITNESS ?= certificates/kn11-degree17-witness-v2.bin
KN11_COMPACT_MANIFEST ?= certificates/kn11-degree17-certificate-v2.json
KN11_EXPECTED_MANIFEST_SHA256 ?=
KN11_EXPECTED_WITNESS_SHA256 ?=
KN11_EXPECTED_SOURCE_SPECIFICATION ?=
KN11_EXPECTED_ROUNDING_SPECIFICATION ?=
KN11_EXPECTED_VERIFICATION_SPECIFICATION ?=
KN11_EXPECTED_RELEASE_COMMIT ?=
KN11_EXPECTED_JULIA_SHA256 ?=
KN11_EXPECTED_JULIA_TREE_SHA256 ?=
KN11_EXPECTED_EXACT_INPUT_SHA256 ?=

export KN11_EXPECTED_MANIFEST_SHA256
export KN11_EXPECTED_WITNESS_SHA256
export KN11_EXPECTED_SOURCE_SPECIFICATION
export KN11_EXPECTED_ROUNDING_SPECIFICATION
export KN11_EXPECTED_VERIFICATION_SPECIFICATION
export KN11_EXPECTED_RELEASE_COMMIT
export KN11_EXPECTED_JULIA_SHA256
export KN11_EXPECTED_JULIA_TREE_SHA256
export KN11_EXPECTED_EXACT_INPUT_SHA256
export JULIA
export JULIA_NUM_THREADS

.PHONY: instantiate test test-supervisor test-verifier \
	test-compact-witness test-cpp-witness samples structure residual-space \
	cross-language schema-audit smoke smoke-exact reproduce fixed round \
	resume-fixed verify-projection \
	export-certificate verify-witness verify-certificate \
	verify-release-certificate dependency-integrity manifest verify-manifest \
	check release-check paper release-assets verify-release-assets \
	verify-zenodo

instantiate:
	$(JULIA_RUN) -e 'using Pkg; Pkg.instantiate(); Pkg.precompile()'

test:
	$(JULIA_RUN) test/runtests.jl

test-supervisor:
	$(PYTHON) -m unittest discover -s test -p 'test_*.py' -v

test-verifier:
	$(PYTHON) -m unittest discover -s verifier/tests -v

test-compact-witness:
	$(JULIA_RUN) test/write_compact_witness_fixture.jl
	$(PYTHON) test/check_compact_witness_roundtrip.py

test-cpp-witness: test-compact-witness
	$(MAKE) -C verifier/cpp clean test test-external

dependency-integrity:
	$(JULIA_RUN) --compiled-modules=no scripts/verify_dependency_integrity.jl

samples:
	$(JULIA_RUN) scripts/certify_samples.jl

structure:
	$(JULIA_RUN) scripts/certify_structure.jl

residual-space:
	$(JULIA_RUN) scripts/certify_residual_space.jl

cross-language:
	$(JULIA_RUN) scripts/certify_cross_language_formulation.jl
	$(PYTHON) test/check_cross_language_formulation.py

schema-audit:
	$(JULIA_RUN) scripts/audit_explicit_schema.jl

smoke:
	$(JULIA_RUN) scripts/smoke_solve.jl

smoke-exact:
	$(JULIA_RUN) scripts/smoke_exact_rounding.jl
	$(PYTHON) test/check_smoke_compact_witness.py

reproduce:
	/usr/bin/python3 -I -E -s tools/run_with_limits.py \
		--wall-seconds 86400 --rss-gib 48 \
		--environment-profile numerical-solve \
		--log logs/degree17-numerical.log -- /usr/bin/env \
		JULIA_DEPOT_PATH=$(JULIA_DEPOT_PATH) JULIA_NUM_THREADS=$(JULIA_NUM_THREADS) \
		OPENBLAS_NUM_THREADS=1 $(JULIA) --startup-file=no --history-file=no \
		--project=. \
		scripts/reproduce_numerical.jl

fixed:
	/usr/bin/python3 -I -E -s tools/run_with_limits.py \
		--wall-seconds 86400 --rss-gib 48 \
		--environment-profile numerical-solve \
		--log logs/degree17-fixed.log -- /usr/bin/env \
		JULIA_DEPOT_PATH=$(JULIA_DEPOT_PATH) JULIA_NUM_THREADS=$(JULIA_NUM_THREADS) \
		OPENBLAS_NUM_THREADS=1 $(JULIA) --startup-file=no --history-file=no \
		--project=. \
		scripts/solve_fixed_objective.jl

resume-fixed:
	/usr/bin/python3 -I -E -s tools/run_with_limits.py \
		--wall-seconds 10800 --rss-gib 48 \
		--environment-profile numerical-solve \
		--log logs/degree17-fixed-resume.log -- /usr/bin/env \
		JULIA_DEPOT_PATH=$(JULIA_DEPOT_PATH) JULIA_NUM_THREADS=$(JULIA_NUM_THREADS) \
		OPENBLAS_NUM_THREADS=1 $(JULIA) --startup-file=no --history-file=no \
		--project=. \
		scripts/resume_fixed_objective.jl

round:
	/usr/bin/python3 -I -E -s tools/run_with_limits.py \
		--wall-seconds 21600 --rss-gib 24 \
		--environment-profile numerical-solve \
		--log logs/degree17-rounding.log -- /usr/bin/env \
		JULIA_DEPOT_PATH=$(JULIA_DEPOT_PATH) JULIA_NUM_THREADS=$(JULIA_NUM_THREADS) \
		OPENBLAS_NUM_THREADS=1 $(JULIA) --startup-file=no --history-file=no \
		--project=. \
		scripts/round_exact_solution.jl

verify-projection:
	/usr/bin/python3 -I -E -s tools/run_with_limits.py \
		--wall-seconds 14400 --rss-gib 24 \
		--environment-profile numerical-solve \
		--log logs/degree17-projection-verification.log -- /usr/bin/env \
		JULIA_DEPOT_PATH=$(JULIA_DEPOT_PATH) JULIA_NUM_THREADS=$(VERIFY_JULIA_NUM_THREADS) \
		OPENBLAS_NUM_THREADS=1 $(JULIA) --startup-file=no --history-file=no \
		--project=. \
		scripts/verify_projection_checkpoint.jl

export-certificate:
	JULIA_NUM_THREADS=$(EXPORT_JULIA_NUM_THREADS) \
	/usr/bin/python3 -I -E -s tools/run_with_limits.py \
		--wall-seconds 14400 --rss-gib 16 \
		--environment-profile certificate-export \
		--log logs/degree17-certificate-export.log -- \
		/usr/bin/python3 -I -E -s \
		tools/export_compact_certificate.py

verify-witness:
	$(PYTHON) verifier/verify_compact_certificate.py $(KN11_COMPACT_WITNESS)

verify-certificate:
	$(PYTHON) tools/run_with_limits.py --wall-seconds 7200 --rss-gib 16 \
		--log logs/degree17-independent-verification.log -- \
		$(PYTHON) verifier/verify_compact_package.py $(KN11_COMPACT_MANIFEST)

verify-release-certificate:
	/usr/bin/python3 -I -E -s tools/release_check.py --certificate-only

manifest:
	python3 tools/release_manifest.py

verify-manifest:
	python3 tools/release_manifest.py --check

paper:
	test -n "$(TECTONIC)"
	test -n "$(TECTONIC_ARCHIVE)"
	test -f "$(TECTONIC_ARCHIVE)"
	test "$$($(TECTONIC) --version)" = "Tectonic 0.17.0"
	mkdir -p build/paper build/tectonic-cache
	SOURCE_DATE_EPOCH=$(SOURCE_DATE_EPOCH) \
	XDG_CACHE_HOME="$(CURDIR)/build/tectonic-cache" \
		$(TECTONIC) \
			--bundle $(TECTONIC_BUNDLE_URL) \
			--outdir build/paper \
			--keep-logs \
			paper/main.tex
	test -s build/paper/main.pdf
	test "$$(head -c 5 build/paper/main.pdf)" = "%PDF-"
	! grep -E "Overfull|Underfull|LaTeX Warning|Undefined" \
		build/paper/main.log

release-assets:
	test -f build/paper/main.pdf
	$(PYTHON) tools/build_release_assets.py \
		--ref $(RELEASE_REF) $(RELEASE_TAG_OPTION) \
		--paper build/paper/main.pdf

verify-release-assets:
	$(PYTHON) tools/build_release_assets.py \
		--check \
		--ref $(RELEASE_REF) $(RELEASE_TAG_OPTION) \
		--paper build/paper/main.pdf

verify-zenodo:
	test -n "$(ZENODO_RECORD_ID)"
	$(PYTHON) tools/verify_zenodo_record.py \
		--record-id "$(ZENODO_RECORD_ID)" \
		--release-dir dist/release

check: dependency-integrity test test-supervisor test-verifier test-compact-witness \
	test-cpp-witness samples structure residual-space cross-language \
	schema-audit smoke smoke-exact verify-manifest

release-check:
	@printf '%s\n' \
		'Refusing: authoritative release verification must start outside the worktree.' \
		'Use the externally supplied env -i and zsh -f bootstrap documented in docs/REPRODUCIBILITY.md.' \
		>&2
	@exit 2
