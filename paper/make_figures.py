"""Render manuscript figures from the accompanying scientific result tables."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import pandas as pd

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
OUT=ROOT/'figures'
OUT.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.labelsize':8,
                     'axes.titlesize':8,'legend.fontsize':7,'pdf.fonttype':42,'ps.fonttype':42,
                     'axes.spines.top':False,'axes.spines.right':False})
COLORS={'OP':'#0072B2','LA':'#D55E00','MLP':'#009E73',
        'Random':'#0072B2','Degree':'#D55E00','Read':'#009E73','Greedy':'#CC79A7'}
STYLES={'Random':'-','Degree':'--','Read':'-.','Greedy':':','OP':'-','LA':'--','MLP':'-.'}

def grouped(ax,data,category,x,y):
    for name,g in data.groupby(category,sort=False):
        agg=g.groupby(x)[y].agg(['mean','min','max']).reset_index()
        ax.plot(agg[x],agg['mean'],label=name,color=COLORS[name],linestyle=STYLES[name],linewidth=1.4)
        ax.fill_between(agg[x],agg['min'],agg['max'],alpha=.12,color=COLORS[name],linewidth=0)
    ax.grid(alpha=.18,linewidth=.5)

d=pd.read_csv(DATA/'mapping_curves.csv')
fig,axs=plt.subplots(1,2,figsize=(4.8,2.25))
for ax,key,ylabel in zip(axs,['ndcg','arr'],['nDCG@10','Agreement@10']):
    grouped(ax,d,'map','fraction',key)
    ax.set(xlabel='Target-vector access fraction',ylabel=ylabel,xlim=(0,1))
    ax.set_xticks([0,.25,.5,.75,1])
axs[0].axhline(.36867136984,color='#666666',linestyle=':',linewidth=1,label='Old / old')
axs[0].axhline(.49963254106,color='#222222',linestyle='--',linewidth=.8,label='Full new')
axs[1].axhline(.39660493827,color='#666666',linestyle=':',linewidth=1)
axs[1].axhline(1,color='#222222',linestyle='--',linewidth=.8)
handles,labels=axs[0].get_legend_handles_labels()
fig.legend(handles,labels,loc='lower center',ncol=5,frameon=False,bbox_to_anchor=(.5,-.01))
fig.tight_layout(rect=[0,.1,1,1],pad=.6)
fig.savefig(OUT/'mapping_curves.pdf');plt.close(fig)

d=pd.read_csv(DATA/'fiqa_policies.csv')
fig,ax=plt.subplots(figsize=(4.8,1.95))
for _,r in d.iterrows():
    ax.plot(r['arr'],r['ndcg'],'o',color=COLORS[r['policy']],markersize=5)
    offsets={'Random':(-7,8),'Degree':(6,1),'Read':(-12,8),'Greedy':(-8,-13)}
    ax.annotate(r['policy'],(r['arr'],r['ndcg']),xytext=offsets[r['policy']],textcoords='offset points',fontsize=8)
ax.set(xlabel='Agreement@10 with exact target',ylabel='Judged nDCG@10',xlim=(.38,.425),ylim=(.222,.294))
ax.grid(alpha=.18);fig.tight_layout(pad=.6);fig.savefig(OUT/'policy_tradeoff.pdf');plt.close(fig)

d=pd.read_csv(DATA/'msmarco_curves.csv');t=pd.read_csv(DATA/'aol_curves.csv')
fig,axs=plt.subplots(1,2,figsize=(4.8,2.25))
grouped(axs[0],d,'policy','fraction','arr')
grouped(axs[1],t,'policy','week','arr')
axs[0].set(xlabel='Target-vector access fraction',ylabel='Agreement@10',title='MS MARCO 50k: known queries',xlim=(0,1))
axs[0].set_xticks([0,.25,.5,.75,1])
axs[1].set(xlabel='Evaluation week',ylabel='Log-row-weighted agreement@10',title='AOL 50k: subsequent weeks')
axs[1].set_xticks([2,4,6,8])
handles,labels=axs[0].get_legend_handles_labels()
fig.legend(handles,labels,loc='lower center',ncol=4,frameon=False,bbox_to_anchor=(.5,-.01))
fig.tight_layout(rect=[0,.1,1,1],pad=.6);fig.savefig(OUT/'workload_curves.pdf');plt.close(fig)

fig,ax=plt.subplots(figsize=(4.8,1.28));ax.set(xlim=(0,10),ylim=(0,3));ax.axis('off')
for x,text,color in [(0.1,'Old document\nvectors', '#E7F0F6'),(3.35,'Mapped vectors\n+ paid target vectors','#E3F0E8'),(7.1,'New query encoder\n+ mixed retrieval','#F8E9D8')]:
    ax.add_patch(FancyBboxPatch((x,1.35),2.75,1.1,boxstyle='round,pad=.08',facecolor=color,edgecolor='#555555',linewidth=.6))
    ax.text(x+1.375,1.9,text,ha='center',va='center',fontsize=8)
for x1,x2 in [(2.9,3.23),(6.18,6.98)]:ax.annotate('',xy=(x2,1.9),xytext=(x1,1.9),arrowprops={'arrowstyle':'->','lw':1})
ax.annotate('Budgeted selection and vector replacement',xy=(4.72,1.18),xytext=(4.72,.4),ha='center',fontsize=8,
            arrowprops={'arrowstyle':'->','lw':.8})
fig.tight_layout(pad=.1);fig.savefig(OUT/'procedure.pdf');plt.close(fig)
print('Rendered four vector figures')
