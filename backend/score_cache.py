"""Chunked inference cache; background aggregation must not monopolize inference."""
import numpy as np


def score_frame(frame, predictor, final, build_lock, inference_lock, batch_size=2048):
    with build_lock:
        if not frame.attrs.get('f8_scored'):
            for family in ('stuff', 'location', 'pitching'):
                values = []
                for start in range(0, len(frame), batch_size):
                    rows = frame.iloc[start:start+batch_size].to_dict('records')
                    with inference_lock:
                        values.extend(predictor.predict(rows, family)['score'].tolist())
                frame[family+'_plus'] = np.array(values, dtype=float)
            frame.attrs['f8_scored'] = True
        if final is not None and not frame.attrs.get('final_scored'):
            output = []
            for start in range(0, len(frame), batch_size):
                rows = frame.iloc[start:start+batch_size].to_dict('records')
                with inference_lock:
                    output.extend(final.records(rows))
            frame['stuff_final'] = [r['score'] for r in output]
            frame['final_history_n'] = [r['history_n'] for r in output]
            frame['final_history_status'] = [r['history_status'] for r in output]
            frame.attrs['final_scored'] = True
    return frame
