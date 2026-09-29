from collections import defaultdict
from statistics import mean, pstdev
from django.conf import settings
from .models import Project, Score

CRITERIA={'functionality':0.4,'quality':0.35,'innovation':0.25}

def weighted_score(criteria,weights=None):
    weights=weights or CRITERIA
    if any(key not in criteria or type(criteria[key]) is not int or not 1<=criteria[key]<=5 for key in weights):
        return None
    return sum(criteria[key]*weight for key,weight in weights.items())

def standings(event):
    """Normalize judge harshness by centering on each judge's own mean.

    Flat judges (variance zero) contribute a neutral 3.0 rather than divide by zero.
    The output keeps raw and adjusted values visible so an organizer can inspect drift.
    """
    weights=event.rubric or CRITERIA
    scores_qs=Score.objects.filter(project__event=event,judge__event=event,project__duplicate_of__isnull=True,project__draft=False)
    if settings.DEMO: scores_qs=scores_qs.filter(project__team__members__isnull=True)
    scores=list(scores_qs.select_related('project','judge'))
    by_judge=defaultdict(list)
    for score in scores:
        value=weighted_score(score.criteria,weights)
        if value is not None: by_judge[score.judge_id].append(value)
    judge_stats={key:(mean(values),pstdev(values)) for key,values in by_judge.items()}
    by_project=defaultdict(list)
    for score in scores:
        raw=weighted_score(score.criteria,weights)
        if raw is None: continue
        center,spread=judge_stats[score.judge_id]
        adjusted=3.0 if spread==0 else max(1,min(5,3+(raw-center)/spread))
        by_project[score.project_id].append((raw,adjusted))
    rows=[]
    projects=Project.objects.filter(event=event,duplicate_of__isnull=True,draft=False)
    if settings.DEMO: projects=projects.filter(team__members__isnull=True)
    for project in projects.order_by('slug'):
        values=by_project.get(project.pk,[])
        rows.append({'project':project.slug,'title':project.title,'reviews':len(values),'raw':round(mean(x[0] for x in values),3) if values else None,'normalized':round(mean(x[1] for x in values),3) if values else None})
    ordered=sorted(rows,key=lambda r:(r['normalized'] is None,-r['normalized'] if r['normalized'] is not None else 0,r['project']))
    last_value=None
    for position,row in enumerate(ordered,1):
        value=row['normalized']
        row['rank']=None if value is None else (ordered[position-2]['rank'] if position>1 and value==last_value else position)
        last_value=value
    # A second ordering describes rank movement without exposing judge IDs,
    # ballots or individual-score distributions. Ties use the same competition ranks.
    raw_ordered=sorted((r for r in rows if r['raw'] is not None),key=lambda r:(-r['raw'],r['project']))
    raw_ranks={}
    last_raw=None
    last_rank=None
    for position,row in enumerate(raw_ordered,1):
        last_rank = last_rank if row['raw'] == last_raw else position
        raw_ranks[row['project']]=last_rank
        last_raw=row['raw']
    for row in ordered:
        row['raw_rank']=raw_ranks.get(row['project'])
        row['rank_movement']=raw_ranks[row['project']]-row['rank'] if row['rank'] is not None else None
        row['rank_movement_abs']=abs(row['rank_movement']) if row['rank_movement'] is not None else None
    return ordered
