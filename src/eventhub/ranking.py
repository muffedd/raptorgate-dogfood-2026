from collections import defaultdict
from statistics import mean, pstdev
from .models import Project, Score

CRITERIA={'functionality':0.4,'quality':0.35,'innovation':0.25}

def weighted_score(criteria,weights=None):
    weights=weights or CRITERIA
    if any(key not in criteria or not isinstance(criteria[key],int) or not 1<=criteria[key]<=5 for key in weights):
        return None
    return sum(criteria[key]*weight for key,weight in weights.items())

def standings(event):
    """Normalize judge harshness by centering on each judge's own mean.

    Flat judges (variance zero) contribute a neutral 3.0 rather than divide by zero.
    The output keeps raw and adjusted values visible so an organizer can inspect drift.
    """
    weights=event.rubric or CRITERIA
    scores=list(Score.objects.filter(project__event=event,judge__event=event,project__duplicate_of__isnull=True).select_related('project','judge'))
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
    for project in Project.objects.filter(event=event,duplicate_of__isnull=True).order_by('slug'):
        values=by_project.get(project.pk,[])
        rows.append({'project':project.slug,'title':project.title,'reviews':len(values),'raw':round(mean(x[0] for x in values),3) if values else None,'normalized':round(mean(x[1] for x in values),3) if values else None})
    return sorted(rows,key=lambda r:(r['normalized'] is None,-r['normalized'] if r['normalized'] is not None else 0,r['project']))
