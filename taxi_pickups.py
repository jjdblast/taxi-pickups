import sys
import MySQLdb
from sklearn.metrics import mean_squared_error
from math import sqrt
from models import *

AGGREGATED_PICKUPS = 'pickups_aggregated'
TRIP_DATA = 'trip_data'

# The `Dataset` class interfaces with the data.
class Dataset(object):
    '''
    Usage:
        dataset = Dataset(0.7, 20) # 14 examples in train set, 6 in test set
        while dataset.hasMoreTrainExamples():
            train_examples = dataset.getTrainExamples(batch_size=2)
            # Do something with the training examples...

        while dataset.hasMoreTestExamples():
            test_example = dataset.getTestExample()
            # Do something with the test example...
    '''

    def __init__(self, train_fraction, dataset_size, table_name):
        self.db = MySQLdb.connect(
            host="localhost", user="root", passwd="",  db="taxi_pickups")

        # The id of the last examples in the train and test set, respectively.
        self.last_train_id = int(train_fraction * dataset_size)
        self.last_test_id = dataset_size

        # The id of the next example to be fetched.
        self.current_example_id = 1
        self.table_name = table_name # table to read examples from

    def hasMoreTrainExamples(self):
        return self.current_example_id <= self.last_train_id

    def hasMoreTestExamples(self):
        return self.current_example_id <= self.last_test_id

    def getTrainExamples(self, batch_size=1):
        '''
        :param batch_size: number of training examples to return
        :return: training examples represented as a list of tuples
        '''
        if self.current_example_id + batch_size - 1 > self.last_train_id:
            batch_size = self.last_train_id - self.current_example_id + 1

        examples = self._getExamples(
            self.current_example_id, num_examples=batch_size)
        self.current_example_id += batch_size
        return examples

    def getTestExample(self):
        '''
        :return: test example, represented as a tuple.
        '''
        if self.current_example_id > self.last_test_id:
            raise Exception("Cannot access example %d: outside specified " \
                            "dataset size range of %d." \
                            % (self.current_example_id, self.last_test_id))

        if self.current_example_id <= self.last_train_id:
            self.current_example_id = self.last_train_id + 1

        example = self._getExamples(self.current_example_id, num_examples=1)[0]
        self.current_example_id += 1
        return example

    def _getExamples(self, start_id, num_examples=1):
        '''
        :param start_id: id of first row to fetch
        :param num_examples: number of examples to return
        :return: examples (i.e. rows) from the data table represented as a list
                    of tuples.
        '''
        cursor = self.db.cursor()
        end_id = start_id + num_examples - 1

        query_string = "SELECT * FROM %s WHERE id BETWEEN %d AND %d" \
                        % (self.table_name, start_id, end_id)

        cursor.execute(query_string)
        self.db.commit()
        return cursor.fetchall()


# The `Evaluator` class evaluates a trained model.
class Evaluator(object):

    def __init__(self, model, dataset):
        self.model = model
        self.dataset = dataset

    def evaluate(self):

        # Test the model.
        test_data, true_num_pickups = self.model.generateTestData()

        # Generate a predicted number of pickups for every example in the test
        # data.
        predicted_num_pickups = []
        for test_example in test_data:
            predicted_num_pickups.append(self.model.predict(test_example))

        # Evaluate the predictions.
        self.evaluatePredictions(true_num_pickups, predicted_num_pickups)

    def evaluatePredictions(self, true_num_pickups, predicted_num_pickups):
        '''
        Prints some metrics on how well the model performed, including the RMSD.

        :param predicted_num_pickups: List of predicted num_pickups.
        :param true_num_pickups: List of observed num_pickups.

        '''
        assert(len(true_num_pickups) == len(predicted_num_pickups))

        print 'True number of pickups:\t\t' + str(true_num_pickups)
        print 'Predicted number of pickups:\t' + str(predicted_num_pickups)

        # Compute the RMSD
        rms = sqrt(mean_squared_error(true_num_pickups, predicted_num_pickups))
        print 'RMSD: %f' % rms


def getModel(model_name):
    if model_name == 'baseline':
        return Baseline()
    raise Exception("No model with name %s" % model_name)

def main(args):
    if len(args) < 2:
        print 'Usage: taxi_pickups model'
        exit(1)

    # Instantiate the specified learning model.
    model = getModel(args[1])
    dataset = Dataset(0.7, 20, AGGREGATED_PICKUPS)
    evaluator = Evaluator(model, dataset)

    # Train the model.
    model.train(dataset)

    # Evaluate the model on data from the test set.
    evaluator.evaluate()

if __name__ == '__main__':
    main(sys.argv)
