import tensorflow as tf
import tensorflow.contrib.slim as slim
import numpy as np
import matplotlib.pyplot as plt
try:
    xrange = xrange
except:
    xrange = range

def discount_rewards(r):
    """ take 1D float array of rewards and compute discounted reward """
    discounted_r = np.zeros_like(r)
    running_add = 0
    for t in reversed(xrange(0, r.size)):
        running_add = running_add * .99 + r[t]
        discounted_r[t] = running_add   
    return discounted_r


#https://gist.github.com/danijar/3f3b547ff68effb03e20c470af22c696
#https://danijar.com/variable-sequence-lengths-in-tensorflow/
def length(sequence):
    used = tf.sign(tf.reduce_max(tf.abs(sequence), reduction_indices=2))
    length = tf.reduce_sum(used, reduction_indices=1)
    length = tf.cast(length, tf.int32)
    return length
#https://gist.github.com/danijar/3f3b547ff68effb03e20c470af22c696
#https://danijar.com/variable-sequence-lengths-in-tensorflow/
def last_relevant(output, length):
    batch_size = tf.shape(output)[0]
    max_length = int(output.get_shape()[1])
    output_size = int(output.get_shape()[2])
    index = tf.range(0, batch_size) * max_length + (length - 1)
    flat = tf.reshape(output, [-1, output_size])
    relevant = tf.gather(flat, index)
    return relevant

def updateTargetGraph(tfVars,tau):
    total_vars = len(tfVars)
    op_holder = []
    for idx,var in enumerate(tfVars[0:total_vars//2]):
        op_holder.append(tfVars[idx+total_vars//2].assign((var.value()*tau) + ((1-tau)*tfVars[idx+total_vars//2].value())))
    return op_holder

def updateTarget(op_holder,sess):
    for op in op_holder:
        sess.run(op)


#Using the method the value  

class FrozenValueNetwork():
    def __init__(self):
        pass

    def make_model(self):
        image_model_inputs = Input(shape=X[0].shape,dtype='float32',name='main_image')
        image_model=Conv2D(16, (2, 2), padding='valid', activation='relu')(image_model_inputs)
        image_model=Conv2D(16, (2, 2), padding='valid', activation='relu')(image_model)

        image_model=Conv2D(32, (1,1),strides=2, padding='valid', activation='relu')(image_model)
        image_model=Conv2D(32, (1,1),strides=2, padding='valid', activation='relu')(image_model)

        image_model=Conv2D(8, (1,1),strides=3, padding='same', activation='relu')(image_model)
        image_model=Conv2D(8, (1,1),strides=2, padding='same', activation='relu')(image_model)
        
        image_model=Flatten()(image_model)
        
        gene_model_inputs = Input(shape=X_gene[0].shape,dtype='float32',name='gene_image')
        gene_model=Conv2D(16, (2, 2), padding='valid', activation='relu')(gene_model_inputs)
        gene_model=Conv2D(16, (2, 2), padding='valid', activation='relu')(gene_model)
        
        # gene_model=Conv2D(8, (1,1),strides=3, padding='same', activation='relu')(gene_model)
        #gene_model=Conv2D(8, (1,1),strides=2, padding='same', activation='relu')(gene_model)
        
        gene_model=Flatten()(gene_model)
        
        combined_model=concatenate([image_model,gene_model])
        
        combined_model=Dense(32, activation='relu')(combined_model)
        combined_model=Dense(8, activation='relu')(combined_model)
        combined_model_preditions=Dense(2, activation='softmax')(combined_model)
        model=Model(inputs=[image_model_inputs,gene_model_inputs],outputs=combined_model_preditions)
        model.compile(optimizer='adam', loss='categorical_crossentropy', metrics=['accuracy'])    
        return model


class Qnetwork():
    def __init__(self,h_size,s_size,POPULATION,BATCH,myScope):
        self.genomes= tf.placeholder(shape=[POPULATION,300,3],dtype=tf.int32)   
        self.condition = tf.placeholder(tf.int32, shape=[], name="condition")
        self.correct_action=tf.placeholder(shape=[None], dtype=tf.int32)
        self.correct_mean=tf.placeholder(shape=[None], dtype=tf.float32)
        self.imageIn = tf.placeholder(shape=[None,s_size,s_size,3],dtype=tf.float32)      
        self.used_genomes= tf.placeholder(shape=[None],dtype=tf.int32)
        self.conv1 = slim.conv2d( \
        inputs=self.imageIn,num_outputs=32,kernel_size=[8,8],stride=[4,4],padding='VALID', biases_initializer=None)
        self.conv2 = slim.conv2d( \
            inputs=self.conv1,num_outputs=64,kernel_size=[4,4],stride=[2,2],padding='VALID', biases_initializer=None)
        self.conv3 = slim.conv2d( \
            inputs=self.conv2,num_outputs=64,kernel_size=[3,3],stride=[1,1],padding='VALID', biases_initializer=None)
        self.conv4 = slim.conv2d( \
            inputs=self.conv3,num_outputs=h_size,kernel_size=[7,7],stride=[1,1],padding='VALID', biases_initializer=None)
        #We take the output from the final convolutional layer and split it into separate advantage and value streams.
        self.streamAC,self.streamVC = tf.split(self.conv4,2,3)
        self.streamA = tf.reshape(self.streamAC,[-1,512])
        self.streamV = slim.flatten(self.streamVC)
        xavier_init = tf.contrib.layers.xavier_initializer()
        hidden_conv = slim.fully_connected(self.streamA,h_size//2,biases_initializer=None,activation_fn=tf.nn.relu)
        self.VW=tf.Variable(xavier_init([h_size//2,1]))
        self.Value =tf.cond(self.condition <  1, 
                             lambda: tf.matmul(self.streamV,self.VW), 
                             lambda: tf.reshape(tf.matmul(self.streamV,self.VW),[1,BATCH])[0])
        hidden_conv = tf.cond(self.condition <  1, lambda: tf.tile(hidden_conv,[POPULATION,1]), lambda: hidden_conv)
        
        sequence_output, state = tf.nn.dynamic_rnn(tf.contrib.rnn.LSTMCell(64),\
                                            tf.cast(self.genomes,tf.float32),dtype=tf.float32,sequence_length=length(self.genomes),scope=myScope+'_rnn')
        last = last_relevant(sequence_output, length(self.genomes)) 
        hidden_rnn= slim.fully_connected(last,h_size,biases_initializer=None,activation_fn=tf.nn.relu)
        hidden_rnn_2= slim.fully_connected(hidden_rnn,h_size//2,biases_initializer=None,activation_fn=tf.nn.relu)
        hidden_rnn_final=tf.cond(self.condition < 1, lambda: hidden_rnn_2,lambda: tf.gather(hidden_rnn_2,self.correct_action)) 
        combined=tf.concat([hidden_rnn_final,hidden_conv],1)
        #
        #Change Recurrent Net to Match Inputs in Testing
        #hidden_rnn=tf.cond(self.condition < 1, lambda: hidden_rnn,lambda: tf.gather(hidden_rnn,self.action_holder)) 
        self.hidden_combined= slim.fully_connected(combined,h_size,biases_initializer=None,activation_fn=tf.nn.relu)
        self.hidden_combined_2= slim.fully_connected(self.hidden_combined,h_size//4,biases_initializer=None,activation_fn=tf.nn.relu)
        self.regression= slim.fully_connected(self.hidden_combined_2,1,biases_initializer=None,activation_fn=None)
        self.Advantage=tf.cond(self.condition <  1, 
        lambda: tf.reshape(self.regression,[1,POPULATION]), 
        lambda: tf.reshape(self.regression,[1,BATCH])[0])
        #self.Advantage=tf.reduce_mean(self.Advantage,axis=1,keep_dims=True)
        #Then combine them together to get our final Q-values.
        self.Mean=tf.reduce_mean(self.Advantage,axis=1,keep_dims=False)
        self.Qout=tf.cond(self.condition <  1, 
        lambda: self.Value + tf.subtract(self.Advantage,tf.reduce_mean(self.Advantage,axis=1,keep_dims=True)), 
        lambda: self.Value + self.Advantage-self.correct_mean)

        self.Smooth=tf.subtract(tf.reshape(self.Qout,[POPULATION]),tf.cast(self.used_genomes,tf.float32))
        self.predict = tf.argmax(self.Smooth,0)
        
        #Below we obtain the loss by taking the sum of squares difference between the target and prediction Q values.
        self.targetQ = tf.placeholder(shape=[None],dtype=tf.float32)
        self.actions = tf.placeholder(shape=[None],dtype=tf.int32)
        #self.actions_onehot = tf.one_hot(self.actions,BATCH,dtype=tf.float32)
        
        #self.Q = tf.reduce_sum(tf.multiply(self.Qout, self.actions_onehot), axis=1)
        
        self.td_error = tf.square(self.targetQ - self.Qout)
        self.loss = tf.reduce_mean(self.td_error)
        self.trainer = tf.train.AdamOptimizer(learning_rate=0.0001)
        self.updateModel = self.trainer.minimize(self.loss)

class agent():
    def __init__(self, lr, s_size,a_size,h_size,pop_size):
        #Placeholders
        self.state_in= tf.placeholder(shape=[None,s_size,s_size,1],dtype=tf.float32)
        self.genomes= tf.placeholder(shape=[pop_size,30,3],dtype=tf.int32)       
        self.used_genomes= tf.placeholder(shape=[pop_size],dtype=tf.int32)
        self.training=tf.placeholder(shape=[1],dtype=tf.bool)
        self.reward_holder = tf.placeholder(shape=[None],dtype=tf.float32)
        self.action_holder = tf.placeholder(shape=[None],dtype=tf.int32)
        
        #Convolution Network 
        conv1 = tf.layers.conv2d(inputs=self.state_in,filters=32,kernel_size=[5, 5],padding="same",activation=tf.nn.relu)
        pool1 = tf.layers.max_pooling2d(inputs=conv1, pool_size=[2, 2], strides=2)
        conv2 = tf.layers.conv2d(inputs=pool1,filters=64,kernel_size=[5, 5],padding="same",activation=tf.nn.relu)
        pool2 = tf.layers.max_pooling2d(inputs=conv2, pool_size=[2, 2], strides=2)
        flatten= tf.reshape(pool2,[-1,7*7*64])
        hidden_conv = slim.fully_connected(flatten,64,biases_initializer=None,activation_fn=tf.nn.relu)

        #Recurrent Neural Network
        sequence_output, state = tf.nn.dynamic_rnn(tf.contrib.rnn.LSTMCell(64),\
                                            tf.cast(self.genomes,tf.float32),dtype=tf.float32,sequence_length=length(self.genomes))
        last = last_relevant(sequence_output, length(self.genomes)) 
        hidden_rnn= slim.fully_connected(last,64,biases_initializer=None,activation_fn=tf.nn.relu)

        #Training/Testing Changes
         #Clone Image by Genome Size in Training
        hidden_conv = tf.tile(hidden_conv,[pop_size,1])
        

        combined=tf.concat([hidden_rnn,hidden_conv],1)
        hidden_combined= slim.fully_connected(combined,1024,biases_initializer=None,activation_fn=tf.nn.relu)
        self.regression= slim.fully_connected(hidden_combined,1,biases_initializer=None,activation_fn=tf.nn.sigmoid)
        self.output=tf.reshape(self.regression,[-1])*tf.cast(self.used_genomes,tf.float32)
        self.final_output=tf.nn.softmax(self.output) #Change to log softmax
        self.chosen_action = tf.argmax(self.output,1)




        #The next six lines establish the training proceedure. We feed the reward and chosen action into the network
        #to compute the loss, and use it to update the network.

        self.responsible_output=tf.gather(self.final_output,self.action_holder)
        self.loss = tf.reduce_mean(-tf.log(self.responsible_output)*self.reward_holder)
        tvars = tf.trainable_variables()
        self.gradient_holders = []
        for idx,var in enumerate(tvars):
            placeholder = tf.placeholder(tf.float32,name=str(idx)+'_holder')
            self.gradient_holders.append(placeholder)

        self.gradients = tf.gradients(self.loss,tvars)

        optimizer = tf.train.AdamOptimizer(learning_rate=lr)
        self.update_batch = optimizer.apply_gradients(zip(self.gradient_holders,tvars))