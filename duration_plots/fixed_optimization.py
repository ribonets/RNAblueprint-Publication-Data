from __future__ import print_function

try:
    from PyDesign import *
except ImportError, e:
    print(e.message)
    exit(1)

import RNAblueprint as rbp
import argparse
import sys
import time
import random

def main():
    parser = argparse.ArgumentParser(description='Design a tri-stable example same to Hoehner 2013 paper.')
    parser.add_argument("-f", "--file", type = str, default=None, help='Read file in *.inp format')
    parser.add_argument("-s", "--start", type = str, default=None, help='Read file in with start sequence')
    parser.add_argument("-i", "--input", default=False, action='store_true', help='Read custom structures and sequence constraints from stdin')
    parser.add_argument("-q", "--nupack", default=False, action='store_true', help='Use Nupack instead of the ViennaRNA package (for pseudoknots)')
    parser.add_argument("-n", "--number", type=int, default=100, help='Number of designs to generate')
    parser.add_argument("-s", "--stop", type=int, default=100000, help='Stop optimization run if no better solution is aquired after (stop) trials.')
    parser.add_argument("-m", "--mode", type=str, default='sample_global', help='Mode for getting a new sequence: sample, sample_local, sample_global, sample_strelem')
    parser.add_argument("-k", "--kill", type=int, default=0, help='Timeout value of graph construction in seconds. (default: infinite)')
    parser.add_argument("-g", "--graphml", type=str, default=None, help='Write a graphml file with the given filename.')
    parser.add_argument("-c", "--csv", default=False, action='store_true', help='Write output as semi-colon csv file to stdout')
    parser.add_argument("-p", "--progress", default=False, action='store_true', help='Show progress of optimization')
    parser.add_argument("-d", "--debug", default=False, action='store_true', help='Show debug information of library')
    args = parser.parse_args()

    print("# Options: number={0:d}, stop={1:d}, mode={2:}, nupack={3:}".format(args.number, args.stop, args.mode, str(args.nupack)))
    rbp.initialize_library(args.debug, args.kill)
    # define structures
    structures = []
    constraint = ''
    start_sequence = ''
    
    if (args.input):
        data = ''
        for line in sys.stdin:
            data = data + '\n' + line
        (structures, constraint, start_sequence) = read_input(data)
    elif (args.file is not None):
        print("# Input File: {0:}".format(args.file))
        (structures, constraint, start_sequence) = read_inp_file(args.file)
    else:
        structures = ['((((....))))....((((....))))........',
            '........((((....((((....))))....))))',
            '((((((((....))))((((....))))....))))']
        constraint = 'NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN'
    if (args.start is not None):
        with open(args.start, 'r') as f:
            data = f.read()
            start_sequence = data.rstrip('\n')
            print('# ' + start_sequence)
    # try to construct dependency graph, catch errors and timeouts
    dg = None
    construction_time = 0.0
    sample_time = 0.0
        
    # construct dependency graph with these structures
    try:
        start = time.clock()
        dg = rbp.DependencyGraphMT(structures, constraint)
        construction_time = time.clock() - start
    except Exception as e:
        print( "Error: %s" % e , file=sys.stderr)
    
    # general DG values
    print("# " + "\n# ".join(structures) + "\n# " + constraint)

    if (dg is not None):
        
        # if requested write out a graphml file
        if args.graphml is not None:
            with open(args.graphml, 'w') as f:
                f.write(dg.get_graphml() + "\n")
        
        # print the amount of solutions
        print('# Maximal number of solutions: ' + str(dg.number_of_sequences()))
        # print the amount of connected components
        number_of_components = dg.number_of_connected_components()
        print('# Number of Connected Components: ' + str(number_of_components))
        for i in range(0, number_of_components):
            print('# [' + str(i) + ']' + str(dg.component_vertices(i)))
        
        # remember general DG values
        graph_properties = get_graph_properties(dg)
        # create a initial design object
        if (args.nupack):
            design = nupackDesign(structures, start_sequence)
        else:
            design = vrnaDesign(structures, start_sequence)
        
        # print header for csv file
        if (args.csv):
            print(";".join([
                        "mode",
                        "score",
                        "num_mutations",
                        "construction_time",
                        "sample_time",
                        design.write_csv_header()] +
                        graph_properties.keys()))
        
        samplings = []
        endpoint = math.log(args.stop, 10)
        for i in range(0, int(endpoint)):
            samplings.append(10**i - sum(samplings))
            samplings.append(2*10**i - sum(samplings))
            samplings.append(5*10**i - sum(samplings))

        # main loop from zero to number of solutions
        for n in range(0, args.number):
            # reset the design object
            if (args.nupack):
                design = nupackDesign(structures, start_sequence)
            else:
                design = vrnaDesign(structures, start_sequence)
            # optimize this design further and further
            number_of_mutations = 0
            start = time.clock()
            # print number of mutations for point 0
            score = calculate_objective(design)
            if (args.csv):
                print("\"" + args.mode + "\"",
                    score,
                    number_of_mutations,
                    construction_time,
                    0,
                    design.write_csv(),
                    *graph_properties.values(), sep=";")
            else:
                print(design.write_out(score))
            
            for s in samplings: 
                try:
                    (score, mutations) = fixed_optimization(dg, design, number=s, mode=args.mode, progress=args.progress)
                except ValueError as e:
                    print (e.value)
                    exit(1)
                number_of_mutations += mutations
                sample_time = time.clock() - start
                 
                if (args.csv):
                    print("\"" + args.mode + "\"",
                        score,
                        number_of_mutations,
                        construction_time,
                        sample_time,
                        design.write_csv(),
                        *graph_properties.values(), sep=";")
                else:
                    print(design.write_out(score))
    else:
        print('# Construction time out reached!')

def fixed_optimization(dg, design, objective_function=calculate_objective, weight=0.5, number=100, mode='sample', progress=False):
    '''
    Takes a Design object and does a classic optimization of this sequence.
    :param dg: RNAdesign DependencyGraph object
    :param design: Design object containing the sequence and structures
    :param objective_function: function which takes a design object and returns a score for evaluation
    :param weight: float specifying the weight of the difference part of the objective function
    :param stop: Number of unsuccessful new sequences before stoping the optimization
    :param mode: String defining the sampling mode: sample, sample_global, sample_local
    :param progress: Whether or not to print the progress to the console
    :param return: Optimization score reached for the final sequence
    "param return: Number of samples neccessary to reach this result
    '''
    # if the design has no sequence yet, sample one from scratch
    if not design.sequence:
        dg.sample()
        design.sequence = dg.get_sequence()
    else:
        dg.set_sequence(design.sequence)

    score = objective_function(design, weight)
    # remember how may mutations were done
    number_of_samples = 0
    # modes
    modes = ['sample','sample_global','sample_local']
    # main optimization loop 
    for n in range(0, number):
        # count up the mutations
        number_of_samples += 1
        # sample a new sequence
        if mode == "random":
            (mut_nos, sample_count) = sample_sequence(dg, design, random.choice(modes), 1)
        else:
            (mut_nos, sample_count) = sample_sequence(dg, design, mode, 1)
        
        # write progress
        if progress:
            sys.stdout.write("\rMutate: {0:7.0f}/{1:5.0f} | Score: {2:7.4f} | NOS: {3:.5e}".format(number_of_samples, n, score, mut_nos) + " " * 20)
            sys.stdout.flush()
        
        this_score = objective_function(design, weight)
        # evaluate
        if (this_score < score):
            score = this_score
            count = 0
        else:
            dg.revert_sequence(sample_count)
            design.sequence = dg.get_sequence()
    
    # clear the console
    if (progress):
        sys.stdout.write("\r" + " " * 60 + "\r")
        sys.stdout.flush()
    
    # finally return the result
    return score, number_of_samples


if __name__ == "__main__":
    main()


