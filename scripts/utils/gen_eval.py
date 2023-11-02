# gen_eval.py - generate running scripts for performance evaluation.


import getopt
import os
import sys
from gen_conf import VERSION


class Config:
    def __init__(self):
        self.sid = None        # sample ID
        self.cnv_scale = None  

        self.casper_dir = None
        self.copykat_dir = None
        self.infercnv_dir = None
        self.numbat_dir = None
        self.xclone_dir = None

        self.cell_anno_fn = None
        self.gene_anno_fn = None
        self.truth_fn = None
        self.repo_scripts_dir = None
        self.out_dir = None

        self.plot_sid = None
        self.plot_dec = None

        # intermediate variables
        self.copy_gain_dir = None
        self.copy_loss_dir = None
        self.loh_dir = None


    def check_args(self):
        assert_n(self.sid)
        assert_n(self.cnv_scale)
        if self.cnv_scale not in ("gene", "arm"):
            raise ValueError

        assert_e(self.casper_dir)
        assert_e(self.copykat_dir)
        assert_e(self.infercnv_dir)
        assert_e(self.numbat_dir)
        assert_e(self.xclone_dir)

        assert_e(self.cell_anno_fn)
        assert_e(self.gene_anno_fn)
        assert_e(self.truth_fn)

        assert_n(self.out_dir)
        if not os.path.exists(self.out_dir):
            os.mkdir(self.out_dir)

        assert_e(self.repo_scripts_dir)

        if not self.plot_dec:
            self.plot_dec = CONF_PLOT_DEC


def assert_e(path):
    if path is None or not os.path.exists(path):
        raise OSError


def assert_n(var):
    if var is None or not var:
        raise ValueError


def __get_xclone_prob_dir(conf, cnv_type):
    if cnv_type == "copy_gain":
        return os.path.join(conf.xclone_dir, "prob_combine_copygain")
    elif cnv_type == "copy_loss":
        return os.path.join(conf.xclone_dir, "prob_combine_copyloss")
    elif cnv_type == "loh":
        return os.path.join(conf.xclone_dir, "prob_combine_loh")
    else:
        raise ValueError


def __get_script_prefix(conf):
    return conf.sid + ".eval"


def __generate_r(fn, conf, cnv_type):
    if cnv_type not in ("copy_gain", "copy_loss", "loh"):
        raise ValueError
    cnv_scale = conf.cnv_scale

    s  = '''# This file was generated by "%s (v%s)."
# %s.R - benchmark on %s dataset

library(cardelino)
library(dplyr)
library(ggplot2)
library(stringr)

args <- commandArgs(trailingOnly = TRUE)
work_dir <- args[1]
setwd(work_dir)

source("benchmark.R")
source("main.R")
source("utils.R")
''' % (APP, VERSION, __get_script_prefix(conf), conf.sid)

    s += '''
sid <- "%s"
cnv_type <- "%s"    # could be "copy_gain", "copy_loss", or "loh".
cnv_scale <- "%s"        # could be "gene" or "arm".
''' % (conf.sid, cnv_type, cnv_scale)

    xclone_dir = __get_xclone_prob_dir(conf, cnv_type)
    if cnv_type in ("copy_gain", "copy_loss"):
        s += '''
method_list <- c("casper", "copykat", "infercnv", "numbat", "xclone")
method_sub_list <- c("casper", "copykat", "infercnv", "numbat", "xclone")
mtx_type_list <- c("expr", "expr", "expr", "prob", "prob")
dat_dir_list <- c(
  "%s",
  "%s",
  "%s",
  "%s",
  "%s"
)
''' % (conf.casper_dir, conf.copykat_dir, conf.infercnv_dir, conf.numbat_dir, 
       xclone_dir)

    else:
        s += '''
method_list <- c("casper", "casper", "numbat", "xclone")
method_sub_list <- c("casper_median", "casper_medianDev", "numbat", "xclone")
mtx_type_list <- c("baf", "baf", "prob", "prob")
dat_dir_list <- c(
  "%s",
  "%s",
  "%s",
  "%s"
)
''' % (conf.casper_dir, conf.casper_dir, conf.numbat_dir, xclone_dir)

    s += '''
cell_anno_fn <- "%s"
gene_anno_fn <- "%s"
truth_fn <- "%s"
out_dir <- "result"
''' % (conf.cell_anno_fn, conf.gene_anno_fn, conf.truth_fn)

    s += '''
bm_main(
  sid, cnv_type, cnv_scale, 
  method_list, method_sub_list, mtx_type_list, dat_dir_list,
  cell_anno_fn, gene_anno_fn, truth_fn, out_dir,
  overlap_mode = "customize", filter_func = NULL, 
  metrics = c("ROC", "PRC"), max_n_cutoff = 1000,
  plot_sid = %s,
  plot_dec = %d, plot_legend_xmin = 0.7, plot_legend_ymin = 0.25,
  plot_width = 6.5, plot_height = 5, plot_dpi = 600,
  verbose = TRUE, save_all = FALSE)

''' % ("NULL" if conf.plot_sid is None else '"%s"' % conf.plot_sid,
       conf.plot_dec, )

    with open(fn, "w") as fp:
        fp.write(s)


def generate_r(conf):
    out_fn_list = []
    for cnv_type, out_dir in zip(("copy_gain", "copy_loss", "loh"),
        (conf.copy_gain_dir, conf.copy_loss_dir, conf.loh_dir)):
        out_fn = os.path.join(out_dir, "%s.R" % __get_script_prefix(conf))
        __generate_r(out_fn, conf, cnv_type)
        out_fn_list.append(out_fn)
    return out_fn_list


def __generate_qsub(fn, conf, cnv_type, r_script):
    if cnv_type not in ("copy_gain", "copy_loss", "loh"):
        raise ValueError
    cnv_scale = conf.cnv_scale
    prefix = "%s_%s_%s" % (cnv_scale, cnv_type, conf.sid)

    s  = '''#!/bin/bash
# This file was generated by "%s (v%s)."
''' % (APP, VERSION)

    s += '''#PBS -N %s
#PBS -q cgsd
#PBS -l nodes=1:ppn=5,mem=200g,walltime=100:00:00
#PBS -o %s.out
#PBS -e %s.err
''' % (prefix, prefix, prefix)

    s += '''
source ~/.bashrc
conda activate XCLBM

# run `set` after `source` & `conda activate` as the source file has an unbound variable
set -eux

work_dir=`cd $(dirname $0) && pwd`
if [ -n "$PBS_O_WORKDIR" ]; then
    work_dir=$PBS_O_WORKDIR
fi
'''

    s += '''
scripts_dir=%s
cp  $scripts_dir/evaluate/benchmark.R  $work_dir
cp  $scripts_dir/evaluate/main.R  $work_dir
cp  $scripts_dir/evaluate/utils.R  $work_dir
''' % (conf.repo_scripts_dir, )

    s += '''
Rscript  $work_dir/%s  $work_dir
''' % (r_script, )
    
    s += '''
set +ux
conda deactivate
echo "All Done!"

'''

    with open(fn, "w") as fp:
        fp.write(s)


def generate_qsub(conf):
    out_fn_list = []
    for cnv_type, out_dir in zip(("copy_gain", "copy_loss", "loh"),
        (conf.copy_gain_dir, conf.copy_loss_dir, conf.loh_dir)):
        out_fn = os.path.join(out_dir, "%s.qsub.sh" % __get_script_prefix(conf))
        r_script = "%s.R" %  __get_script_prefix(conf)
        __generate_qsub(out_fn, conf, cnv_type, r_script)
        out_fn_list.append(out_fn)
    return out_fn_list


def generate_run(conf):
    out_fn = os.path.join(conf.out_dir, "run.sh")

    s = '''#!/bin/bash
# This file was generated by "%s (v%s)."
''' % (APP, VERSION)

    for run_dir in (conf.copy_gain_dir, conf.copy_loss_dir, conf.loh_dir):
        s += '''
cd %s
qsub %s.qsub.sh
''' % (run_dir, __get_script_prefix(conf))

    s += '''
echo All Done!

'''

    with open(out_fn, "w") as fp:
        fp.write(s)
  
    return out_fn


def usage(fp = sys.stderr):
    s =  "\n" 
    s += "Version: %s\n" % (VERSION, )
    s += "Usage: %s <options>\n" % (APP, )  
    s += "\n" 
    s += "Options:\n"
    s += "  --sid STR              Sample ID.\n"
    s += "  --cnvScale STR         CNV scale, gene or arm.\n"
    s += "  --outdir DIR           Output dir.\n"
    s += "  --xclone DIR           XClone dir.\n"
    s += "  --numbat DIR           Numbat dir.\n"
    s += "  --casper DIR           CaSpER dir.\n"
    s += "  --copykat DIR          CopyKAT dir.\n"
    s += "  --infercnv DIR         InferCNV dir.\n"
    s += "  --truth FILE           Ground truth file.\n"
    s += "  --cellAnno FILE        Cell annotation file.\n"
    s += "  --geneAnno FILE        Gene annotation file.\n"
    s += "  --repoScripts DIR      Repo scripts dir.\n"
    s += "  --plotSid STR          Sample ID shown in figure.\n"
    s += "  --plotDec INT          Decimal in plots [%d]\n" % CONF_PLOT_DEC
    s += "  --version              Print version and exit.\n"
    s += "  --help                 Print this message and exit.\n"
    s += "\n"

    fp.write(s)


def main():
    func = "main"

    if len(sys.argv) <= 1:
        usage(sys.stderr)
        sys.exit(1)

    conf = Config()
    opts, args = getopt.getopt(sys.argv[1:], "", [
        "sid=", "cnvScale=",
        "outdir=",
        "xclone=", "numbat=",
        "casper=", "copykat=", "infercnv=",
        "truth=", 
        "cellAnno=", "geneAnno=", 
        "repoScripts=",
        "plotSid=", "plotDec=",
        "version", "help"
    ])

    for op, val in opts:
        if len(op) > 2:
            op = op.lower()
        if op in   ("--sid"): conf.sid = val
        elif op in ("--cnvscale"): conf.cnv_scale = val
        elif op in ("--outdir"): conf.out_dir = val
        elif op in ("--xclone"): conf.xclone_dir = val
        elif op in ("--numbat"): conf.numbat_dir = val
        elif op in ("--casper"): conf.casper_dir = val
        elif op in ("--copykat"): conf.copykat_dir = val
        elif op in ("--infercnv"): conf.infercnv_dir = val
        elif op in ("--truth"): conf.truth_fn = val
        elif op in ("--cellanno"): conf.cell_anno_fn = val
        elif op in ("--geneanno"): conf.gene_anno_fn = val
        elif op in ("--reposcripts"): conf.repo_scripts_dir = val
        elif op in ("--plotsid"): conf.plot_sid = val
        elif op in ("--plotdec"): conf.plot_dec = int(val)
        elif op in ("--version"): sys.stderr.write("%s\n" % VERSION); sys.exit(1)
        elif op in ("--help"): usage(); sys.exit(1)
        else:
            sys.stderr.write("[E::%s] invalid option: '%s'.\n" % (func, op))
            return(-1)    

    conf.check_args()

    # create sub dirs.
    conf.copy_gain_dir = os.path.join(conf.out_dir, "copy_gain")
    if not os.path.exists(conf.copy_gain_dir):
        os.mkdir(conf.copy_gain_dir)

    conf.copy_loss_dir = os.path.join(conf.out_dir, "copy_loss")
    if not os.path.exists(conf.copy_loss_dir):
        os.mkdir(conf.copy_loss_dir)

    conf.loh_dir = os.path.join(conf.out_dir, "loh")
    if not os.path.exists(conf.loh_dir):
        os.mkdir(conf.loh_dir)

    # generate R scripts
    r_scripts = generate_r(conf)
    print("R scripts: %s\n" % str(r_scripts))

    # generate qsub scripts
    qsub_scripts = generate_qsub(conf)
    print("qsub scripts: %s\n" % str(qsub_scripts))

    # generate run shell scripts
    run_script = generate_run(conf)
    print("run script: %s\n" % (run_script, ))

    sys.stdout.write("[I::%s] All Done!\n" % func)


APP = "gen_eval.py"

CONF_PLOT_DEC = 3


if __name__ == "__main__":
    main()

