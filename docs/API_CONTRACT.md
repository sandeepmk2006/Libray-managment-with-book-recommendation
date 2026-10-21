# Athenaeum API contract

Backend: Flask (`run.py`) at `http://127.0.0.1:5000`. All responses are JSON. Times are ISO-8601 strings
(local time, no timezone). Errors: `{"error": "message"}` with 4xx status.

The frontend is a static SPA served from `app/static/` (`index.html` at `/`).

## Core
| Method | Path | Response |
|---|---|---|
| GET | `/api/overview` | `{inside_now, visits_today, total_members, total_books, active_loans, overdue_loans, avg_stay_min, busiest_hour, today_hourly:[24 ints]}` |
| POST | `/api/gate/scan` body `{member_id}` | `{action:"entry"\|"exit", member:{member_id,name,department,year}, time, duration_min:null\|float, message}` |
| POST | `/api/gate/simulate` body `{n:int}` | random members enter/exit; `{events:[same as scan]}` (demo helper) |
| GET | `/api/gate/live` | `{inside:[{member_id,name,department,entry_time,minutes}], recent:[{member_id,name,action,time,duration_min}] (latest 25)}` |
| GET | `/api/members?q=&limit=` | `[{member_id,name,department,year,visits,loans}]` |
| GET | `/api/members/<id>` | `{member:{...}, stats:{visits,total_hours,avg_stay_min,loans,late_rate,favourite_genre}, visits:[last 30 {entry_time,exit_time,duration_min,purpose}], loans:[{loan_id,book_id,title,issued,due,returned,status}], taste:{genre:share}}` |
| GET | `/api/books?q=&genre=` | `[{book_id,title,author,genre,year,pages,copies,available,avg_rating,n_ratings}]` |
| GET | `/api/books/<id>` | book object + `similar:[rec items]` |
| GET | `/api/genres` | `[str]` |
| POST | `/api/loans` body `{member_id,book_id}` | loan object |
| POST | `/api/loans/<loan_id>/return` | loan object |

## Recommender (Module 5)
Rec item: `{book:{book_id,title,author,genre,year}, score:float 0..1, reasons:[str]}`

| GET | `/api/recommend/<member_id>?method=hybrid\|content\|user_cf\|item_cf\|svd\|popular&k=10` | `{member_id, method, cold_start:bool, items:[rec item]}` |
| GET | `/api/recommend/similar/<book_id>?k=8` | `{items:[rec item]}` |
| GET | `/api/recommend/evaluate` | `{k, methods:{<name>:{precision,recall,ndcg,hit_rate,coverage,rmse:null\|float}}, protocol:str}` |

## Analytics & ML (Modules 2-4) — implemented in `app/analytics.py`
Each function takes the dict from `app.db.load_frames(conn)` and returns a JSON-serialisable dict
(no numpy types, no NaN — use None).

| Path | Function | Shape |
|---|---|---|
| `/api/analytics/eda` | `eda(frames)` | `{summary:{table:{rows,cols,missing:{col:count}}}, describe:{duration_min:{count,mean,median,std,var,min,q1,q3,max,skew,kurtosis}, ...}, hourly:[24], weekday_hour:[[24]x7], daily:[{date,visits,unique_members,avg_stay}], by_department:[{department,visits,avg_stay,loans,late_rate}], by_purpose:[{purpose,count}], genre_popularity:[{genre,loans,avg_rating}], top_books:[{book_id,title,loans,avg_rating}], correlation:{columns:[..], matrix:[[..]]}, stay_histogram:{bins:[edges], counts:[..]}, outliers:{method:"IQR", lower, upper, count}}` |
| `/api/analytics/hypothesis` | `hypothesis(frames)` | `{tests:[{name, question, h0, h1, test, statistic, p_value, alpha:0.05, decision:"Reject H0"\|"Fail to reject H0", interpretation, effect_size:null\|float}], confidence_intervals:[{metric, mean, low, high, level:0.95}]}` |
| `/api/analytics/forecast` | `forecast(frames)` | `{target:"hourly footfall", models:[{name, r2, mae, rmse, coefficients:{feature:value}\|null}], best, next_24h:[{hour_iso, predicted}], actual_vs_pred:[{x, actual, linear, polynomial, multiple}]}` |
| `/api/analytics/classify` | `classify(frames)` | `{target:"late return", features:[..], class_balance:{late,on_time}, models:[{name, accuracy, precision, recall, f1, roc_auc, confusion:[[tn,fp],[fn,tp]], cv_mean, cv_std}], best, feature_importance:[{feature, importance}], tree_rules:str, roc:{<model>:{fpr:[..],tpr:[..]}}}` |
| `/api/analytics/clusters` | `clusters(frames)` | `{features:[..], elbow:[{k, inertia, silhouette}], chosen_k, kmeans:{points:[{member_id, x, y, cluster}], centroids_profile:[{cluster, size, persona, <feature means>}]}, agglomerative:{silhouette, agreement_ari, dendrogram:{icoord,dcoord,labels}}}` |
| `/api/analytics/predict_late` POST `{member_id, book_id}` | `predict_late(frames, member_id, book_id)` | `{probability, label, top_factors:[{feature, contribution}]}` |

## Graph (Lab: Neo4j)
| GET | `/api/graph/books?min_weight=3` | `{nodes:[{id,title,genre,loans}], links:[{source,target,weight}]}` co-borrow graph |
| GET | `/api/graph/cypher` | text/plain Cypher script to load the same graph into Neo4j |

## Ethics (Module 6)
| GET | `/api/ethics/report` | `{anonymised_sample:[..], k_anonymity:{quasi_identifiers:[..], k, violations}, consent:{opted_in, opted_out}, fairness:{recommendation_exposure_by_gender:{..}, by_department:{..}, disparate_impact:float, late_model_parity:{..}}, transparency:[str]}` |
