# SONARA time display format

## Problem

SONARA stores duration and structural positions as seconds. The metadata dialog
currently renders fractional clock strings such as `3:23.59` and `3:23.3`.
Those strings are numerically correct, but the mixed colon-and-decimal notation
can be mistaken for an hours/minutes/seconds value.

The upstream SONARA summary uses a conventional whole-second clock:

- values below one hour use `m:ss`;
- values of one hour or more use `h:mm:ss`.

## Decision

Render these SONARA Core fields with the upstream whole-second clock:

- `analyzed_duration_seconds`;
- `intro_end_seconds`;
- `outro_start_seconds`.

Round the raw seconds to the nearest whole second before splitting the value
into hours, minutes, and seconds. Keep the stored database values unchanged.

Examples:

| Raw seconds | Display |
|---:|---:|
| `18.0` | `0:18` |
| `199.0` | `3:19` |
| `584.421875` | `9:44` |
| `3723.0` | `1:02:03` |

For the inspected track, the resulting metadata is:

```text
Duration      9:44
Intro end     0:01
Outro start   9:20
```

## Scope

Change only presentation in the frontend metadata dialog. Do not change:

- SONARA analysis or structure heuristics;
- raw database precision;
- API schemas;
- leading or trailing silence formatting;
- beat-grid offset or energy-curve hop formatting.

## Verification

Add focused frontend assertions for:

- seconds-only positions;
- minute positions;
- the inspected 584.421875-second duration;
- hour positions;
- rounding that carries into the next minute.

Run the focused frontend metadata test, then the frontend build.
