import numpy as np, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
a=np.load('enc4tools/v3.npz'); b=np.load('enc4tools/v4.npz')
V3,V4,xs,ys,zs=a['V'],b['V'],a['xs'],a['ys'],a['zs']
def ix(arr,v): return int(np.argmin(abs(arr-v)))
def show(ax,M3,M4,u,v,title,ul,vl):
    img=np.zeros(M4.shape+(3,)); img[:]=1
    img[M3&M4]=(.55,.55,.55); img[M4&~M3]=(.1,.5,1); img[M3&~M4]=(1,.3,.2)
    ax.imshow(img.transpose(1,0,2),origin='lower',extent=[u[0],u[-1],v[0],v[-1]],interpolation='nearest')
    ax.set_title(title,fontsize=8); ax.set_xlabel(ul,fontsize=7); ax.set_ylabel(vl,fontsize=7); ax.tick_params(labelsize=6); ax.grid(alpha=.3)
fig,axs=plt.subplots(3,3,figsize=(18,20))
k=ix(zs,-1.5); show(axs[0,0],V3[:,:,k],V4[:,:,k],xs,ys,'bottom wall Zb -1.5 (look from inside)','Xb','Yb')
i=ix(xs,124.2); show(axs[0,1],V3[i],V4[i],ys,zs,'right wall Xb 124.2','Yb','Zb')
i=ix(xs,-1.5); show(axs[0,2],V3[i],V4[i],ys,zs,'left wall Xb -1.5','Yb','Zb')
for n,yb in enumerate((2,6,12,30,45,60)):
    j=ix(ys,yb); ax=axs[1+n//3,n%3]; show(ax,V3[:,j,:],V4[:,j,:],xs,zs,f'plane Yb {yb} (floor up toward lid); grey both, blue enc4 only, red enc3 only','Xb','Zb')
    ax.set_ylim(-35,205)
plt.tight_layout(); plt.savefig('enc4tools/sec1.png',dpi=70)
fig,axs=plt.subplots(2,4,figsize=(22,13))
for n,zb in enumerate((3,12,20,26,33,40,46,55)):
    k=ix(zs,zb); show(axs[n//4,n%4],V3[:,:,k],V4[:,:,k],xs,ys,f'plane Zb {zb}','Xb','Yb')
plt.tight_layout(); plt.savefig('enc4tools/sec2.png',dpi=70)
fig,axs=plt.subplots(2,4,figsize=(22,13))
for n,xb in enumerate((4,9,20,45,70,95,105,115)):
    i=ix(xs,xb); show(axs[n//4,n%4],V3[i],V4[i],ys,zs,f'plane Xb {xb}','Yb','Zb'); axs[n//4,n%4].set_ylim(-35,90)
plt.tight_layout(); plt.savefig('enc4tools/sec3.png',dpi=70)
