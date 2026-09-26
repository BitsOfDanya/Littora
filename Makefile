PY ?= ml/.venv/bin/python
DETECTOR_BASELINES ?= fdi fdi_rule lgbm rf lgbm_rgb lgbm_bands lgbm_bands_indices
DETECTOR_MODELS ?= raunet raunet_hard unetpp raunet_aux raunet_focal_tversky raunet_focal_dice
DETECTOR_FINAL ?= raunet__marida_mixed__common
DETECTOR_C1 ?= raunet__marida_mixed_c1__common
ENSEMBLE ?= raunet__marida_mixed__common,raunet_hard__marida_l2a__common,unetpp_resnet34__marida_l2a__common

.PHONY: ml-env audit registry splits detector-data detector-baselines detector-marida detector-train detector-ensemble detector-export detector-checks concentration concentration-export satellite drift-check smoke smoke-api ml-all

ml-env:
	python3 -m venv ml/.venv
	ml/.venv/bin/pip install -r ml/requirements.lock
	ml/.venv/bin/pip install --no-deps -e backend -e ml

audit:
	$(PY) -m littora_ml audit

registry:
	$(PY) -m app.case pair

splits:
	$(PY) -m littora_ml splits

detector-data:
	$(PY) -m littora_ml detector prepare

detector-baselines:
	for name in $(DETECTOR_BASELINES); do $(PY) -m littora_ml detector baseline --config configs/detector/$$name.toml || exit 1; done

detector-marida:
	for name in fdi fdi_rule lgbm; do $(PY) -m littora_ml detector baseline --config configs/detector/$$name.toml --data marida --split official || exit 1; done
	$(PY) -m littora_ml detector train --config configs/detector/raunet.toml --data marida --split official
	$(PY) -m littora_ml detector evaluate --run raunet__marida --data marida --split common
	$(PY) -m littora_ml detector evaluate --run raunet__marida --data marida_l2a --split common

detector-train:
	for name in $(DETECTOR_MODELS); do $(PY) -m littora_ml detector train --config configs/detector/$$name.toml || exit 1; done
	$(PY) -m littora_ml detector train --config configs/detector/raunet.toml --data marida_mixed
	$(PY) -m littora_ml detector train --config configs/detector/raunet.toml --data marida_mixed_c1
	$(PY) -m littora_ml detector c1check --service $(DETECTOR_FINAL) --candidates $(DETECTOR_C1)

detector-ensemble:
	$(PY) -m littora_ml detector ensemble --runs raunet__marida_l2a__common,lgbm_pixel__marida_l2a__common
	$(PY) -m littora_ml detector ensemble --runs raunet__marida_l2a__common,raunet_hard__marida_l2a__common
	$(PY) -m littora_ml detector ensemble --runs raunet__marida_l2a__common,raunet_hard__marida_l2a__common,lgbm_pixel__marida_l2a__common
	$(PY) -m littora_ml detector ensemble --runs $(ENSEMBLE)

detector-export:
	$(PY) -m littora_ml detector calibrate --run $(DETECTOR_FINAL)
	$(PY) -m littora_ml detector vessels --run $(DETECTOR_FINAL)
	$(PY) -m littora_ml detector export --run $(DETECTOR_FINAL)
	$(PY) -m littora_ml detector stability --run $(DETECTOR_FINAL)

detector-checks:
	$(PY) -m littora_ml detector regions --config configs/detector/lgbm.toml --data marida_l2a
	$(PY) -m littora_ml detector negatives --run $(DETECTOR_FINAL)
	$(PY) -m littora_ml detector external --source plp
	$(PY) -m littora_ml detector report --figures $(DETECTOR_FINAL):marida_l2a:common

concentration:
	$(PY) -m littora_ml concentration run --config configs/concentration/broad.toml --jobs 6
	$(PY) -m littora_ml concentration run --config configs/concentration/compact.toml --jobs 6
	$(PY) -m littora_ml concentration external

drift-check:
	$(PY) -m littora_ml drift check --stage report
	$(PY) -m littora_ml drift check --stage spread

concentration-export:
	$(PY) -m littora_ml concentration export --config configs/concentration/broad.toml

satellite:
	$(PY) -m littora_ml concentration satellite --run $(DETECTOR_FINAL)

ml-all: audit registry detector-data detector-baselines detector-marida detector-train detector-ensemble detector-export detector-checks concentration concentration-export satellite drift-check splits

smoke:
	$(PY) -m littora_ml detector rescore --runs $(DETECTOR_FINAL),lgbm_pixel__marida_l2a__common,rf_pixel__marida_l2a__common,fdi_rule__marida_l2a__common
	cd backend && $(abspath $(PY)) -m pytest -q
	cd ml && $(abspath $(PY)) -m pytest -q

smoke-api:
	curl -sf http://localhost:8000/api/v1/health
	curl -sf -X POST http://localhost:8000/api/v1/analyses -H 'Content-Type: application/json' -d '{"aoi_id":"novorossiysk","aoi_name":"Новороссийск","bbox":[37.76,44.66,37.9,44.74],"date":"2025-09-04","window_days":1,"scene_id":null,"target":"litter-visual"}' -o /dev/null -w "analysis %{http_code}\n"
	curl -sf http://localhost:8000/api/v1/models -o /dev/null -w "models %{http_code}\n"
