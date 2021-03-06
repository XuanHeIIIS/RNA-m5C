#!bin/usr/env python

#Jianheng Liu @ Zhanglab, SYSU
#Feb, 2018
#Email: liujh26@mail2.sysu.edu.cn
#Usage: This program is used to call m5C sites of a single sample.
#Input: [pileups]

import os,sys
import argparse
from collections import defaultdict,Counter
import copy
import sqlite3
import time
from time import gmtime, strftime
import numpy as np
import math
import scipy.stats
import signal
from multiprocessing import Process,Pool,Manager

def read_CR(input):
	overall = []
	n = 0
	line = input.readline()
	while (line):
		if line.startswith("#"):
			line = line.strip().split("\t")
			if len(line) == 4:
				n += 1
				gene,total,Cs,nonCR = line
				gene = gene.replace("#","")
				if int(total) < options.CT_number or float(nonCR) >= options.gene_CR:
					nonCRs[gene] = 1.0
				else:
					nonCRs[gene] = float(nonCR)
					if gene != "ALL":
						overall.append(float(nonCR))
				if gene in control:
					if int(total) > options.CT_number:
						control[gene] = float(nonCR)
				if gene == "ELSE":
					sys.stderr.write("#No annotation\t%.6f\n" % (float(nonCR)))
				elif gene == "ALL":
					sys.stderr.write("#Overall\t%s\n" % (float(nonCR)))
			else:
				stat,value = line
				# sys.stderr.write("%s\t%s\n" % (stat,value) )
				# if stat == "#Median":
					# nonCRs["Median"] = float(value)
				# elif stat == "#Mean":
					# nonCRs["Mean"] = float(value)
		else:
			sys.stderr.write("#%d of %d genes have CT coverage >= %d\n" % (len(overall),n,options.CT_number))
			nonCRs["Median"] = np.median(overall)
			nonCRs["Mean"] = np.mean(overall)
			nonCRs["discard"] = 1.0
			sys.stderr.write("#Median\t%.8f\n" % nonCRs["Median"])
			sys.stderr.write("#Mean\t%.8f\n" % nonCRs["Mean"])
			sys.stderr.write("#90%%\t%.8f\n" % np.percentile(overall,90))
			sys.stderr.write("#75%%\t%.8f\n" % np.percentile(overall,75))
			sys.stderr.write("#50%%\t%.8f\n" % np.percentile(overall,50))
			sys.stderr.write("#25%%\t%.8f\n" % np.percentile(overall,25))
			sys.stderr.write("#10%%\t%.8f\n" % np.percentile(overall,10))
			break
		line = input.readline() #Note that the first line of data was read
	control_nonCR = []
	if control:
		for key,value in control.items():
			if value != "None":
				control_nonCR.append(value)
		nonCRs["control"] = np.median(control_nonCR)
		sys.stderr.write("[%s] Control number: %d of %d; median: %.6f; mean: %.6f\n" \
		% (strftime("%Y-%m-%d %H:%M:%S", time.localtime()),len(control_nonCR),len(control),np.median(control_nonCR),np.mean(control_nonCR)))
	return line,input

def call_m5C(line,col):
	#line = line.strip().split("\t")
	#10      100007599       -       ENSG00000138131 LOXL4   ENST00000260702 LOXL4-001       protein_coding  1       0       0       0       0       1       1;1,0,0 ...
	chr,pos_1,dir,gene,name,trans,isoform,biotype,total_cov,CT,A_count,T_count,C_count,G_count = line[0:14]
	total_cov = int(total_cov)
	CT = int(CT)
	# if CT/(total_cov+0.0) < options.var_ratio:
		# return None
	if col == -1:
		total_cov_col = total_cov
		CT_col = CT
		C_count_col = int(C_count)
	else:
		total_cov_col,CT_col,C_count_col = line[col].split(";")[1].split(",")
		total_cov_col = int(total_cov_col)
		CT_col = int(CT_col)
		C_count_col = int(C_count_col)
	
	if CT_col >= options.coverage and C_count_col >= options.count:
		ratio = C_count_col / (CT_col + 0.0)
		if ratio < options.ratio or CT/(total_cov+0.0) < options.var_ratio or CT_col/(total_cov_col+0.0) < options.var_ratio:
			return None
			
		nonCR_gene = nonCRs.get(gene)
		
		if nonCR_gene is None:
			nonCR_gene = nonCRs[options.non_anno]
			
		if options.conversion_rate == "gene":
			nonCR = nonCR_gene
		elif options.conversion_rate == "overall":
			if nonCR_gene == 1.0:
				non_CR = 1.0
			else:
				nonCR = nonCRs.get("ALL")
		elif options.conversion_rate == "control":
			if nonCR_gene == 1.0:
				nonCR = 1.0
			else:
				nonCR = nonCRs.get("control")
		#else:
		if options.method == "binomial":
			pvalue = scipy.stats.binom_test(C_count_col, n=CT_col, alternative='greater', p=nonCR)
		elif options.method == "fisher":
			pass
		elif options.method == "poisson":
			pvalue = scipy.stats.poisson.sf(C_count_col, int(ceil(nonCR*CT_col)))
		
		if pvalue < options.pvalue:
			Signal = total_cov_col/(total_cov+0.0)
			if Signal >= options.signal:
				if nonCR_gene < 0.00001:
					nonCR_format = format(nonCR_gene,'.1e')
				else:
					nonCR_format = str(round(nonCR_gene,5))
				if pvalue < 0.001:
					P_format = format(pvalue,'.1e')
				else:
					P_format = str(round(pvalue,3))
				LINE = "\t".join([chr,pos_1,dir,gene,name,trans,isoform,biotype,nonCR_format])
				LINE = LINE + "\t" + ",".join(line[8:14])
				LINE = LINE + "\t" + "\t".join([str(total_cov_col),str(CT_col),str(C_count_col),str(round(ratio,5)),P_format,str(round(Signal,6))]) 
				LINE = LINE + "\t" + "|".join([i for i in line[14:]]) + "\n"
				return LINE
	else:
		return None
	
if __name__ == "__main__":
	description = """
	"""
	parser = argparse.ArgumentParser(prog="m5C_caller",fromfile_prefix_chars='@',description=description,formatter_class=argparse.RawTextHelpFormatter)
	#Require
	group_required = parser.add_argument_group("Required")
	group_required.add_argument("-i","--input",dest="input",required=True,help="input pileup, sorted")
	group_required.add_argument("-o","--output",dest="output",required=True,help="output prefix. file names are [prefix].[C-cutoff].txt")
	#Filter
	group_site = parser.add_argument_group("m5C filter")
	group_site.add_argument("-c","--coverage",dest="coverage",default=20,type=int,help="C+T coverage, default=10")
	group_site.add_argument("-C","--count",dest="count",default=3,type=int,help="C count, below which the site will not count, default=3")
	group_site.add_argument("-r","--ratio",dest="ratio",default=0.1,type=float,help="m5C level/ratio, default=0.1")
	group_site.add_argument("-p","--pvalue",dest="pvalue",default=0.05,type=float,help="pvalue, default=0.05")
	group_site.add_argument("-s","--signal",dest="signal",default=0.9,type=float,help="signal ratio, equals coverage(under C-cutoff)/coverage, default=0.9")
	group_site.add_argument("-R","--var_ratio",dest="var_ratio",default=0.8,type=float,help="the ratio cutoff of CT/Total to filter sequencing/mapping errors, default=0.8")
	group_site.add_argument("-g","--gene",dest="gene_CR",default=0.05,type=float,help="conversion rate, over which a gene will be discarded, default=0.05")
	group_site.add_argument("-N","--CT",dest="CT_number",default=1000,type=int,help="CT count, below which a gene will be discarded, default=1000")
	#Statistics
	group_stat = parser.add_argument_group("Statistic method")
	group_stat.add_argument("--method",dest="method",default="binomial",choices=['binomial', 'fisher', 'poisson'],help="statistical method: binomial, fisher exact test, or poisson, default=binomial")
	group_stat.add_argument("--CR",dest="conversion_rate",default="gene",choices=['gene','overall','control'],help="conversion rate used: gene or overall, default=gene")
	group_stat.add_argument("--NA",dest="non_anno",default="ELSE",choices=['ELSE','Median','Mean','ALL','discard'],help="which CR to use if no aene annotation, default=ELSE")
	group_stat.add_argument("--control",dest="control",help="control list, median non-conversion rate will be used")
	group_stat.add_argument("--cutoff",dest="C_cutoffs",default="3,None",help="C-cutoffs, 1-10,15,20 or None, seperated by comma, default=3,None")
	#Version
	group_other = parser.add_argument_group("Other")
	group_other.add_argument("--version",action="version",version="%(prog)s 1.0")
	options = parser.parse_args()
	
	#sys.stderr.write("[%s] Running with %d processors, pid [%s]\n" % (strftime("%Y-%m-%d %H:%M:%S", time.localtime()),options.processors,str(os.getpid())))
	sys.stderr.write("[%s] Running, pid [%s]\n" % (strftime("%Y-%m-%d %H:%M:%S", time.localtime()),str(os.getpid())))
	sys.stderr.write("[%s] Reading header...\n" % (strftime("%Y-%m-%d %H:%M:%S", time.localtime())))
	
	control = {}
	if options.conversion_rate == "control":
		if not options.control:
			raise IOError("control list not given, exit.\n")
		else:
			with open(options.control,'r') as input:
				for line in input.readlines():
					control[line.strip()] = "None"
	
	C_cutoffs = options.C_cutoffs.split(",")
	for i in xrange(len(C_cutoffs)):
		if C_cutoffs[i] not in ['1','2','3','4','5','6','7','8','9','10','15','20','None']:
			raise ValueError("%s not in C-cutoffs, exit.\n" % C_cutoffs[i]) 
			
	sys.stderr.write("[%s] C-cutoffs = [%s]\n" % (strftime("%Y-%m-%d %H:%M:%S", time.localtime()),", ".join(C_cutoffs)))
	
	C_cutoff_cols = {}
	col_start = 14
	n = 0
	for i in ['1','2','3','4','5','6','7','8','9','10','15','20','None'][:-1]:
		C_cutoff_cols[i] = 14 + n
		n += 1
	C_cutoff_cols["None"] = -1
	
	sys.stderr.write("[%s] Analyzing, using [%s] conversion rates...\n" % (strftime("%Y-%m-%d %H:%M:%S", time.localtime()),options.conversion_rate))
	with open(options.input,'r') as input:
		#init
		#signal.signal(signal.SIGINT,signal_handler)
		#pool = multiprocessing.Pool(options.processors)
		#manager = Manager()
		#CRs = manager.dict()
		nonCRs = {}
		results = defaultdict(list)
		line,input = read_CR(input)
		
		while (line):
			line = line.strip().split("\t")
			for C_cutoff in C_cutoffs:
				col = C_cutoff_cols.get(C_cutoff)
				result = call_m5C(line,col)
				if result is not None:
					results[C_cutoff].append(result)
			line = input.readline()
#		try:
#			while (line):
#				for C_cutoff in C_cutoff_cols:
#					col = C_cutoff_cols.get(C_cutoff)
				#result = pool.apply_async(call_m5C,args=(line,col,))
#				result = call_m5C(line,col)
#				if result is not None:
#					results[C_cutoff].append(result)
#				line = input.readline()
#			pool.join()
#		finally:
#			pool.terminate()
	sys.stderr.write("[%s] Writing to disk...\n" % (strftime("%Y-%m-%d %H:%M:%S", time.localtime())))
	for key,records in results.iteritems():
		with file(options.output+"."+key+".txt",'w') as output:
			for record in records:
				output.write(record)
		sys.stderr.write("[%s] %s written.\n" % (strftime("%Y-%m-%d %H:%M:%S", time.localtime()),options.output+"."+key+".txt"))
	sys.stderr.write("[%s] Finished successfully!\n" % (strftime("%Y-%m-%d %H:%M:%S", time.localtime())))
